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
import type { PlaceView } from '../sheets/placeView';
import { SheetScene3D } from '../sheets/scene3d';
import type { ApplyResult, Level } from '../sheets/placeService';
import type { SheetPlacement } from '../sheets/placement';
import { sanitizePlacement } from '../sheets/placement';
import type { Sheet, SheetDoc } from '../sheets/model';
import type { ExportedFile } from '../markup/controller';
import type { Markup, MarkupKind, MarkupSet } from '../markup/model';
import { attachmentOf, newMarkup } from '../markup/model';
import { attachGuids } from '../bcf/attach';
import { fitSimilarity } from '../sheets/placement';
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
      /** Stage 2: placing sheets in the model. */
      levels(): Level[];
      placement(sheetId: string): SheetPlacement | null;
      /** Place a sheet from a placement record (the same one the placement view makes). Returns the result; `moved` asks for `confirmed`. */
      setPlacement(sheetId: string, p: SheetPlacement, o?: { confirmed?: boolean }): ApplyResult;
      removePlacement(sheetId: string): void;
      /** Sheet and model points to a placement: the same fit the placement view does (2 pairs exact, 3 or more least squares). */
      placeByPairs(sheetId: string, pairs: Array<{ sheet: [number, number]; model: [number, number] }>, o?: { level?: number; confirmed?: boolean }): ApplyResult & { residual?: number };
      /** The placement view: open for a sheet, its state, and the client pixels of sheet and model points (to click on). */
      place: {
        open(sheetId: string): boolean;
        close(): void;
        state(): ReturnType<PlaceView['state']> | null;
        clientOfSheet(ux: number, uy: number): [number, number] | null;
        clientOfModel(x: number, y: number): [number, number] | null;
      };
      /** The plan cut at a level: elements and outline counts, bounds. */
      cut(elevation: number): { z: number; elements: number; polylines: number; guids: string[] };
      /** The outlines of the plan cut at a level, per element: GlobalId, class, polylines (plan metres, IFC frame). */
      cutPolys(elevation: number): Array<{ guid: string; cls: string; box: [number, number, number, number]; polys: Array<{ pts: number[]; closed: boolean }> }>;
      /** Geo-referencing: what the PDF says, and what the model has. */
      geo(sheetId: string): { found: string | null; note: string | null; mapConversion: boolean };
      /** Show a placed sheet in 3D (the quad); its state; the sheet sketches drawn in 3D now. */
      show3d(sheetId: string, on: boolean): void;
      quad(sheetId: string): ReturnType<SheetScene3D['state']>;
      setQuadOpacity(v: number): void;
      scene3d(): { drawn: number; renders: { base: number; sharp: number } };
      /** The model overlay on the sheet viewer. */
      overlay(sheetId: string, on: boolean): void;
      overlayState(): { on: boolean; opacity: number; drawn: number; misfit: string | null };
      /** The attachment a sketch has: per markup, its attachment kind and GlobalIds. */
      attachments(setId: string): Array<{ id: string; kind: string; guids: string[]; reason?: string }>;
      /** The viewpoint (components, camera) a sketch on a placed sheet would raise. */
      viewpointOf(setId: string): { components: string[]; hasCamera: boolean } | null;
    };
  }
}

let ctl: SheetsController | null = null;
let sceneTick: (() => void) | null = null;

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

    // ---- placement: the placement view (a chunk of its own), the 3D quads and sketches, the switch of the issues
    c.place.views = issues.views;
    issues.views.sheet = {
      anchor: (set, m) => c.place.anchorPoint(set, m),
      framing: (set) => c.place.framing(set),
      leave: () => { c.close(); },
    };
    const scene = new SheetScene3D(c, app);
    sceneTick = () => scene.tick();
    let pview: PlaceView | null = null;
    let pbuilding: Promise<PlaceView> | null = null;
    c.showPlace = (id) => {
      void (async () => {
        if (!pview && id) {
          pbuilding ??= import('../sheets/placeView').then((m) => (pview = new m.PlaceView(c, stage)));
          await pbuilding;
        }
        await pview?.show(id);
      })();
    };

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
        const added = mk.add(m, set);
        c.attachNew(set, added);
        return added;
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
      levels: () => c.place.levels(),
      placement: (id) => c.store.sheet(id)?.placement ?? null,
      setPlacement: (id, p, o) => {
        const clean = sanitizePlacement(p);
        return clean ? c.place.apply(id, clean, o ?? {}) : { ok: false, error: 'Not a placement' };
      },
      removePlacement: (id) => c.place.remove(id),
      placeByPairs: (id, pairs, o) => {
        const lv = c.place.levels()[o?.level ?? 0];
        const f = fitSimilarity(pairs);
        if (!lv || !f.ok) return { ok: false, error: !lv ? 'No level' : f.ok ? '' : f.error };
        const p: SheetPlacement = {
          kind: 'manual', level: { ...(lv.guid ? { storeyGuid: lv.guid } : {}), name: lv.name, elevation: lv.elevation }, plane: 'plan', transform: f.transform,
          ...(f.residual !== undefined ? { residual: f.residual } : {}), source: `${pairs.length} points`, pairs,
        };
        const r = c.place.apply(id, p, o?.confirmed ? { confirmed: true } : {});
        return { ...r, ...(f.residual !== undefined ? { residual: f.residual } : {}) };
      },
      place: {
        open: (id) => c.openPlace(id),
        close: () => c.closePlace(),
        state: () => pview?.state() ?? null,
        clientOfSheet: (x, y) => pview?.clientOfSheet(x, y) ?? null,
        clientOfModel: (x, y) => pview?.clientOfModel(x, y) ?? null,
      },
      cut: (z) => {
        const k = c.place.cut(z);
        return { z: k.z, elements: k.elements.length, polylines: k.elements.reduce((a, e) => a + e.polys.length, 0), guids: k.elements.map((e) => e.guid) };
      },
      cutPolys: (z) => c.place.cut(z).elements.map((e) => ({ guid: e.guid, cls: e.cls ?? '', box: e.box, polys: e.polys.map((q) => ({ pts: q.pts, closed: q.closed })) })),
      geo: (id) => ({ found: c.store.sheet(id)?.geo?.summary ?? null, note: c.place.geoNotes.get(id) ?? null, mapConversion: !!c.place.mapConversion }),
      show3d: (id, on) => c.setShow3d(id, on),
      quad: (id) => scene.state(id),
      setQuadOpacity: (v) => c.setQuadOpacity(v),
      scene3d: () => ({ drawn: scene.drawnCount(), renders: { ...scene.renders } }),
      overlay: (id, on) => c.setOverlay(id, on),
      overlayState: () => {
        const st = viewer?.state();
        const sh = viewer?.sheet;
        return { on: !!sh && c.overlayOn.has(sh.id), opacity: c.overlayOpacity, drawn: st?.overlayDrawn ?? 0, misfit: sh?.placement?.residual !== undefined ? `${Math.round(sh.placement.residual * 1e4) / 10}` : null };
      },
      attachments: (setId) => {
        const set = mk.get(setId);
        const sheet = set ? c.sheetOfSet(set) : undefined;
        if (!set) return [];
        return set.markups.map((m) => {
          const a = attachmentOf(m);
          const d = sheet ? c.place.derive(m, sheet) : null;
          return { id: m.id, kind: a.kind, guids: attachGuids(a), ...(d ? { reason: d.reason } : {}) };
        });
      },
      viewpointOf: (setId) => {
        const set = mk.get(setId);
        const vp = set ? c.place.viewpointFor(set) : null;
        return vp ? { components: vp.selection.map((s) => s.ifcGuid ?? ''), hasCamera: !!vp.camera } : null;
      },
    };
  },

  onFrame(): void {
    sceneTick?.();
  },

  onModel(): void {
    ctl?.onModel();
    ctl?.emit();
  },
};
