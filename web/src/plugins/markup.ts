// Markup plugin: internal-coordination markup without a BCF topic. Sets of (saved view + markups), drawing tools
// (clouds, text and callouts, highlights, shapes), PDF and JSON export, and restore from either file. Logic in
// src/markup (model, geometry, layout, pdf, report, controller, view, ui); this file wires the tool, the key, the panel
// folder, the params section, the file drop and window.__xrayMarkup. See docs-features/markup.md.

import type GUI from 'lil-gui';
import type { AppPlugin, ViewerApp } from '../app';
import { getAction, registerAction } from '../input/actions';
import { registerTool } from '../tools/registry';
import { registerParamSection } from '../ui/params';
import { MarkupController, toolInfo } from '../markup/controller';
import { PDF_RESOLUTIONS } from '../markup/controller';
import type { ExportedFile, ImportReport, PdfResolution, ToolId } from '../markup/controller';
import { MarkupView } from '../markup/view';
import { buildDrawer, installDrop, markupFileInput, pickMarkupFile } from '../markup/ui';
import { attachmentOf, newMarkup } from '../markup/model';
import type { ColourKey, Markup, MarkupKind, MarkupSet, Weight } from '../markup/model';
import type { PageSize } from '../markup/report';
import { VIEWLOCK_MODES } from '../bcf/attach';
import type { AttachDescription, Attachment, LockState, ViewLockMode } from '../bcf/attach';
import type { RestoreResult } from './views';

export interface MarkupAddSpec {
  kind: MarkupKind;
  /** Shapes: points in canvas CSS pixels, as a drag draws them (rect, ellipse, line, arrow, highlight box: 2 corners). */
  points?: Array<[number, number]>;
  /** Shapes: points as fractions of the view of the set camera, with the depth of their plane (as stored in the file). */
  fractions?: { points: Array<[number, number]>; depth: number };
  /** Callout, text, pointer: a click position on the model, canvas CSS pixels. */
  at?: [number, number];
  /** Measurement: the id of a measurement of the measure tool. */
  measurementId?: number;
  text?: string;
  colour?: ColourKey;
  weight?: Weight;
  fill?: boolean;
  status?: 'open' | 'resolved';
  assignee?: string;
  due?: string;
}

declare global {
  interface Window {
    __xrayMarkup?: {
      /** The sets of the session: id, title, counts, whether it is the active one. */
      list(): Array<{ id: string; title: string; markups: number; open: number; resolved: number; active: boolean }>;
      /** A copy of a set (view, camera, markups, comments). */
      get(id: string): MarkupSet | null;
      /** A new set from the current view; it becomes the active one. */
      create(title?: string): MarkupSet;
      /** Add a markup to a set (default: the active one). Shapes in canvas pixels or as fractions; anchored kinds by a click position. */
      add(spec: MarkupAddSpec, setId?: string): Markup;
      remove(markupId: string): boolean;
      comment(markupId: string, text: string): boolean;
      update(markupId: string, patch: { text?: string; status?: 'open' | 'resolved'; assignee?: string; due?: string; colour?: ColourKey }): boolean;
      undo(): boolean;
      redo(): boolean;
      /** Bring a set's view back and make it active. */
      restore(setId: string, opts?: { animate?: boolean }): RestoreResult;
      /** PDF of some sets (default all): the clean view, the marked view and the table. `download` also saves the file. */
      exportPdf(opts?: { ids?: string[]; page?: PageSize; resolution?: PdfResolution; download?: boolean }): Promise<ExportedFile>;
      /** Capture a set's view again from the current camera; shapes stay on the model (default) or on the screen. Undoable. */
      updateView(setId: string, opts?: { keep?: 'model' | 'screen' }): { shapes: number; moved: number; kept: number };
      exportJson(opts?: { ids?: string[]; download?: boolean }): ExportedFile;
      /** Open a markup JSON text (restores the first set's view). */
      importJson(text: string): Promise<ImportReport>;
      /** Open a markup PDF or JSON file. */
      importFile(file: File | Blob): Promise<ImportReport>;
      /** A BCF topic from a set, or from one markup of it. Returns the topic guid. */
      toBcf(setId: string, markupId?: string): Promise<string>;
      /** What a shape is attached to, and the words of its chip. Anchored markups map their anchor 1:1. */
      attachment(markupId: string): { attach: Attachment; description: AttachDescription } | null;
      /** Change the attachment of a shape (undoable): `none` is view-locked. Measurement and penetration need their link. */
      setAttachment(markupId: string, how: 'none' | 'elements' | 'surface' | 'region' | 'measurement' | 'penetration', link?: { measurement?: Attachment['measurement']; penetration?: Attachment['penetration'] }): boolean;
      /** View-locked markups in 3D: "near view + pin" (default), "pin only" or "hidden". */
      viewLocked3d: ViewLockMode;
      /** The view-lock state of the live camera against the active set's camera. */
      readonly lock: LockState | undefined;
      tool: ToolId;
      setTool(t: ToolId): void;
      readonly selected: string | null;
      readonly status: string;
      /** The markup under a canvas position, or null. */
      hitTest(x: number, y: number): string | null;
      /** True while the live camera is away from the active set's view. */
      readonly away: boolean;
      page: PageSize;
      pdfResolution: PdfResolution;
    };
  }
}

const ICON =
  '<svg viewBox="0 0 20 20" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round">' +
  '<path d="M5.5 14.5a2.4 2.4 0 0 1-.4-4.6 3 3 0 0 1 3.2-3.2 3 3 0 0 1 5.4.6 2.6 2.6 0 0 1 1.4 5 2.6 2.6 0 0 1-3.3 2.2 3 3 0 0 1-3.1.6 2.6 2.6 0 0 1-3.2-.6z"/></svg>';

function obj(v: unknown): Record<string, unknown> {
  return v && typeof v === 'object' ? (v as Record<string, unknown>) : {};
}

let ctl: MarkupController | null = null;
let view: MarkupView | null = null;

export const markupPlugin: AppPlugin = {
  name: 'markup',

  install(app: ViewerApp): void {
    const c = new MarkupController(app);
    ctl = c;
    const v = new MarkupView(c);
    view = v;

    registerTool({
      id: 'markup',
      label: 'Markup',
      title: 'Markup: draw clouds, notes, highlights and shapes on a saved view, then export a PDF or JSON (key K)',
      icon: ICON,
      order: 85,
      drawerWidth: 340,
      panel: (container) => buildDrawer(container, c, v),
    });

    const gui = app.panel;
    if (gui) buildGui(gui, c);

    registerParamSection('markup', {
      collect: () => ({ page: c.page, pdfResolution: c.pdfResolution, weight: c.weight, fill: c.fill, viewLocked3d: c.viewLocked3d }),
      apply: (value, bad, path) => {
        const o = obj(value);
        if (o['page'] !== undefined) {
          if (o['page'] === 'A4' || o['page'] === 'Letter') c.page = o['page'];
          else bad.push(`${path}.page`);
        }
        if (o['pdfResolution'] !== undefined) {
          const r = PDF_RESOLUTIONS.find((x) => x === o['pdfResolution']);
          if (r !== undefined) c.pdfResolution = r;
          else bad.push(`${path}.pdfResolution`);
        }
        if (o['weight'] !== undefined) {
          if (o['weight'] === 1 || o['weight'] === 2 || o['weight'] === 3 || o['weight'] === 4) c.weight = o['weight'];
          else bad.push(`${path}.weight`);
        }
        if (o['fill'] !== undefined) {
          if (typeof o['fill'] === 'boolean') c.fill = o['fill'];
          else bad.push(`${path}.fill`);
        }
        if (o['viewLocked3d'] !== undefined) {
          const v = VIEWLOCK_MODES.find((x) => x === o['viewLocked3d']);
          if (v !== undefined) c.viewLocked3d = v;
          else bad.push(`${path}.viewLocked3d`);
        }
        gui?.controllersRecursive().forEach((k) => k.updateDisplay());
      },
    });

    registerAction({
      id: 'markup.toggle',
      label: 'Markup: open or close the tool',
      group: 'Panels',
      keys: ['k'],
      description: 'Open the Markup drawer to draw on a saved view, or close it',
      run: (a) => getAction('tool.markup')?.run(a),
    });
    registerAction({ id: 'markup.new', label: 'Markup: new set from view', group: 'Markup', keys: [], run: () => { try { c.newSet(); } catch (e) { c.setStatus(e instanceof Error ? e.message : String(e)); } } });
    registerAction({ id: 'markup.open', label: 'Markup: open PDF or JSON file', group: 'Markup', keys: [], run: () => pickMarkupFile(c) });
    registerAction({ id: 'markup.pdf', label: 'Markup: export PDF of all sets', group: 'Markup', keys: [], run: () => void c.downloadPdf().catch((e) => c.setStatus(e instanceof Error ? e.message : String(e))) });
    registerAction({ id: 'markup.json', label: 'Markup: export JSON of all sets', group: 'Markup', keys: [], run: () => { try { c.downloadJson(); } catch (e) { c.setStatus(e instanceof Error ? e.message : String(e)); } } });

    installDrop(c);
    markupFileInput(c); // the hidden picker input exists from the start (scripts and tests can feed it)

    const sets = (): MarkupSet => {
      const s = c.active;
      if (!s) throw new Error('No markup set: create one first');
      return s;
    };
    window.__xrayMarkup = {
      list: () => c.list(),
      get: (id) => {
        const s = c.get(id);
        return s ? (JSON.parse(JSON.stringify(s)) as MarkupSet) : null;
      },
      create: (t) => c.newSet(t),
      add: (spec, setId) => {
        const set = setId ? c.get(setId) : sets();
        if (!set) throw new Error(`No markup set ${setId}`);
        if (set.id !== c.activeId) c.activeId = set.id;
        const tool = TOOL_FOR_KIND(spec.kind, spec.points?.length ?? 0);
        const style = { ...(spec.colour ? { colour: spec.colour } : {}), ...(spec.weight ? { weight: spec.weight } : {}), ...(spec.fill !== undefined ? { fill: spec.fill } : {}), ...(spec.text ? { text: spec.text } : {}) };
        let m: Markup | null;
        if (spec.fractions) {
          m = c.add(newMarkup(spec.kind, { author: c.author.trim() || 'unknown', colour: spec.colour ?? c.colour(tool), weight: spec.weight ?? c.weight, fill: spec.fill ?? c.fill, text: spec.text ?? '', shape: { points: spec.fractions.points, depth: spec.fractions.depth } }), set);
        } else if (spec.measurementId !== undefined) m = c.linkMeasurement(spec.measurementId, spec.text ?? '');
        else if (spec.points) m = c.addShape(tool, spec.points, style);
        else if (spec.at) m = c.addAnchored(tool, spec.at[0], spec.at[1], spec.text ?? '', style);
        else throw new Error('A markup needs points, fractions, at or measurementId');
        if (!m) throw new Error('The markup could not be placed');
        if (spec.status || spec.assignee || spec.due) c.patch(m.id, { ...(spec.status ? { status: spec.status } : {}), ...(spec.assignee ? { assignee: spec.assignee } : {}), ...(spec.due ? { due: spec.due } : {}) }, { noHistory: true });
        return m;
      },
      remove: (id) => c.remove(id),
      comment: (id, t) => c.comment(id, t),
      update: (id, p) => c.patch(id, p),
      undo: () => c.undo(),
      redo: () => c.redo(),
      restore: (id, o) => c.restore(id, o?.animate ?? true),
      exportPdf: (o) => (o?.download ? c.downloadPdf(o) : c.exportPdf(o)),
      exportJson: (o) => (o?.download ? c.downloadJson(o.ids) : c.exportJson(o?.ids)),
      updateView: (id, o) => c.updateView(id, o?.keep ?? c.updateKeep),
      importJson: (t) => c.importJson(t),
      importFile: (f) => c.importFile(f),
      toBcf: (s, m) => c.toBcf(s, m),
      attachment: (id) => {
        const f = c.markup(id);
        return f ? { attach: JSON.parse(JSON.stringify(attachmentOf(f.m))) as Attachment, description: c.describe(f.m) } : null;
      },
      setAttachment: (id, how, link) => c.setAttachment(id, how, link),
      get viewLocked3d() {
        return c.viewLocked3d;
      },
      set viewLocked3d(v: ViewLockMode) {
        c.setViewLocked3d(v);
      },
      get lock() {
        return c.lockState();
      },
      get tool() {
        return c.tool;
      },
      setTool: (t) => c.setTool(t),
      get selected() {
        return c.selected;
      },
      get status() {
        return c.status;
      },
      hitTest: (x, y) => v.hitTest(x, y),
      get away() {
        return c.away();
      },
      get page() {
        return c.page;
      },
      set page(p: PageSize) {
        c.page = p;
      },
      get pdfResolution() {
        return c.pdfResolution;
      },
      set pdfResolution(r: PdfResolution) {
        c.pdfResolution = r;
      },
    };
  },

  onModel(): void {
    ctl?.onModel();
  },

  afterFrame(): void {
    view?.tick();
  },
};

/** The tool that draws a kind (for scripts). Cloud with more than 2 points is the freehand cloud. */
function TOOL_FOR_KIND(kind: MarkupKind, nPoints: number): ToolId {
  if (kind === 'cloud') return nPoints > 2 ? 'cloudFree' : 'cloud';
  const t = (['text', 'callout', 'pointer', 'highlight', 'highlightBox', 'rect', 'ellipse', 'line', 'arrow', 'polyline', 'polygon', 'pen'] as ToolId[]).find((x) => toolInfo(x).kind === kind);
  return t ?? 'select';
}

function buildGui(gui: GUI, c: MarkupController): void {
  const folder = gui.addFolder('Markup');
  folder.close();
  const actions = {
    open: () => pickMarkupFile(c),
    create: () => { try { c.newSet(); } catch (e) { c.setStatus(e instanceof Error ? e.message : String(e)); } },
    pdf: () => void c.downloadPdf().catch((e) => c.setStatus(e instanceof Error ? e.message : String(e))),
    json: () => { try { c.downloadJson(); } catch (e) { c.setStatus(e instanceof Error ? e.message : String(e)); } },
  };
  folder.add(actions, 'create').name('New markup set from view');
  folder.add(actions, 'open').name('Open markup file');
  folder.add(actions, 'pdf').name('Export markup PDF');
  folder.add(actions, 'json').name('Export markup JSON');
  folder.add(c, 'page', ['A4', 'Letter']).name('Markup page size');
  folder.add(c, 'pdfResolution', ['screen', 150, 200, 300]).name('Markup PDF resolution (dpi)');
  folder.add(c, 'viewLocked3d', [...VIEWLOCK_MODES]).name('Markup view-locked in 3D').onChange((v: string) => c.setViewLocked3d(v));
  const st = new Proxy({} as { status: string }, { get: () => c.status, set: () => true });
  const ctrl = folder.add(st, 'status').name('Markup status').disable();
  c.onChange(() => ctrl.updateDisplay());
}
