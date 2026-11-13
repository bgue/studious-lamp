// Sheets: PDF drawing sheets as a part of the review. This controller opens a PDF as a sheet set (one sheet per page), keeps the
// sheets and their bytes (store.ts), makes the sketches drawn on them (MarkupSets with a sheet frame, shared with the 3D sketches),
// imports the annotations a PDF already has, exports a marked-up copy of the PDF on its own layer, and raises a sheet sketch as an
// issue. The PDF libraries are not imported here: pdfSession.ts is loaded by a dynamic import on first use. DOM only for the
// canvases of thumbnails and snapshots and for downloads; the viewer is viewer.ts and the panel ui.ts. Docs: docs-features/sheets.md.

import type * as PdfJs from 'pdfjs-dist';
import type { ViewerApp } from '../app';
import type { BcfController } from '../bcf/controller';
import { drawOps } from '../bcf/annotate';
import type { Ctx2D } from '../bcf/annotate';
import type { BcfSheetRef, BcfTopic, BcfViewpointRef } from '../bcf/model';
import { newGuid } from '../bcf/model';
import type { MarkupController } from '../markup/controller';
import type { ExportedFile, ImportReport } from '../markup/controller';
import { bounds as ptsBounds } from '../markup/geometry';
import { SHEET_CAMERA, SHEET_VIEW, isSheetSet, newMarkupId, nowIso, sanitizeSet, uniqueSetTitle } from '../markup/model';
import type { Markup, MarkupSet, ModelIdentity } from '../markup/model';
import { loadedIdentity, scopeOf } from '../markup/scope';
import { sanitizeView } from '../views/model';
import type { SavedView } from '../views/model';
import { specToMarkups } from './annot';
import { layoutSheetMarkup } from './layout';
import { boxOf, docIdOf, parseSheetId, sha256Hex, sheetIdOf, sheetName, sheetUnit, userToDisplay } from './model';
import { readGeoPage } from './geoPdf';
import { PlaceService } from './placeService';
import { placementStatus } from './placement';
import type { Sheet, SheetDoc } from './model';
import type { PdfSession } from './pdfSession';
import { SheetStore } from './store';

export type SheetPdfLoader = () => Promise<PdfSession>;

export interface OpenReport {
  ok: boolean;
  error?: string;
  /** The doc (an existing one when the same bytes were open already). */
  docId?: string;
  pages: number;
  /** Our annotations rebuilt as editable shapes, and the others read as read-only. */
  own: number;
  foreign: number;
  existing: boolean;
  warnings: string[];
}

const THUMB_W = 200;
/** Thumbnails are made for the first pages only: a 300-page set must open quickly (the others show a plain card). */
const MAX_THUMBS = 40;
const SNAP_MAX = 1280;

function download(name: string, bytes: Uint8Array, type: string): void {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([bytes as Uint8Array<ArrayBuffer>], { type }));
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

/** The status words of a placed sheet. */
function placementWords(sh: Sheet): string {
  return placementStatus(sh.placement);
}

const slug = (s: string): string => s.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^\w.-]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 60) || 'sheet';

export class SheetsController {
  readonly store: SheetStore;
  /** Placement of sheets in the model: levels, plan cut, geo, attachment (placeService.ts). */
  readonly place: PlaceService;
  /** Sheets shown in 3D as a textured quad (session), and the opacity of all of them. */
  readonly shown3d = new Set<string>();
  quadOpacity = 0.6;
  /** Model overlay on the sheet: per sheet on or off, and the opacity of the lines. */
  readonly overlayOn = new Set<string>();
  overlayOpacity = 0.7;
  /** The sheet that is being placed (the placement view is up), or null. */
  placeId: string | null = null;
  /** Set by the plugin: show the placement view for a sheet / hide it. */
  showPlace: ((sheetId: string | null) => void) | null = null;
  /** The sheet that is open in the viewer, or null (the 3D view is showing). */
  openId: string | null = null;
  status = 'No sheets yet';
  busy = false;
  /** Set by the plugin: show the viewer for a sheet / hide it. */
  showViewer: ((sheetId: string | null) => void) | null = null;
  private readonly listeners = new Set<() => void>();
  private readonly proxies = new Map<string, Promise<PdfJs.PDFDocumentProxy>>();
  private sessionP: Promise<PdfSession> | null = null;
  private saveTimer: ReturnType<typeof setTimeout> | null = null;
  private lastSaved = '';
  private adopting = false;
  private readonly seenDocs = new WeakSet<object>();

  constructor(readonly app: ViewerApp, readonly markup: MarkupController, readonly bcf: BcfController | null, private readonly loader: SheetPdfLoader = () => import('./pdfSession').then((m) => m.session()), store?: SheetStore) {
    this.store = store ?? new SheetStore();
    this.place = new PlaceService(this);
    markup.openPdfSheets = (file, bytes) => this.openBytes(bytes, (file as File).name ?? '').then((r) => this.asImportReport(r));
    markup.sheetRestore = (set) => this.openSet(set);
    markup.onChange(() => this.scheduleSave());
    markup.onRemoved((set) => { if (isSheetSet(set)) this.scheduleSave(); });
    bcf?.onChange(() => {
      this.adoptViewpoints();
      void this.openBcfDocuments().catch(() => undefined);
    });
  }

  // ---------------------------------------------------------------- events, small state

  onChange(cb: () => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }
  emit(): void {
    for (const l of this.listeners) l();
  }
  setStatus(t: string): void {
    this.status = t;
    this.emit();
  }
  private get who(): string {
    return this.markup.author.trim() || 'unknown';
  }

  /** The PDF libraries (loaded on the first call). */
  session(): Promise<PdfSession> {
    if (!this.sessionP) {
      this.sessionP = this.loader();
      this.sessionP.catch(() => { this.sessionP = null; });
    }
    return this.sessionP;
  }

  // ---------------------------------------------------------------- start: the saved sheets

  /** Read the saved sheets and their sketches (no PDF library is loaded for this). */
  async init(): Promise<void> {
    const meta = await this.store.init();
    if (meta) {
      for (const raw of meta.sets) {
        const r = sanitizeSet(raw);
        if (typeof r === 'string' || !isSheetSet(r.set)) continue;
        if (this.markup.get(r.set.id)) continue;
        this.markup.adoptSet(r.set);
      }
      this.lastSaved = JSON.stringify(this.sheetSets());
      if (this.store.docs.length) this.status = `${this.store.docs.length} PDF${this.store.docs.length === 1 ? '' : 's'} from the last session`;
    }
    this.emit();
  }

  // ---------------------------------------------------------------- what is there

  get identity(): ModelIdentity | null {
    return this.markup.loaded ? loadedIdentity(this.app as never) : null;
  }

  /** The docs of the loaded model (same, revised, unknown) and the docs of other models, hidden. */
  docs(): { here: SheetDoc[]; other: SheetDoc[] } {
    const now = this.identity;
    const here: SheetDoc[] = [];
    const other: SheetDoc[] = [];
    for (const d of this.store.docs) (scopeOf(d.model, now).visible ? here : other).push(d);
    return { here, other };
  }

  sheetsOf(docId: string): Sheet[] {
    return this.store.sheets.filter((s) => s.docId === docId).sort((a, b) => a.page - b.page);
  }

  /** The sketches drawn on a sheet (editable and read-only), in order. */
  sketchesOn(sheetId: string): MarkupSet[] {
    return this.markup.sets.filter((s) => s.frame?.kind === 'sheet' && s.frame.sheet === sheetId);
  }
  sheetSets(): MarkupSet[] {
    return this.markup.sets.filter((s) => isSheetSet(s));
  }
  sheetOfSet(set: MarkupSet): Sheet | undefined {
    return set.frame?.kind === 'sheet' ? this.store.sheet(set.frame.sheet) : undefined;
  }
  /** The sketches that wait for a PDF that is not open (their sheet is unknown). */
  orphans(): MarkupSet[] {
    return this.sheetSets().filter((s) => !this.sheetOfSet(s));
  }

  // ---------------------------------------------------------------- opening a PDF

  /** Open a PDF file as sheets. */
  async openFile(file: File | Blob): Promise<OpenReport> {
    const bytes = new Uint8Array(await file.arrayBuffer());
    return this.openBytes(bytes, (file as File).name ?? 'drawing.pdf');
  }

  private asImportReport(r: OpenReport): ImportReport {
    return { ok: r.ok, ...(r.error ? { error: r.error } : {}), sets: r.own + (r.foreign ? 1 : 0), markups: r.own + r.foreign, added: r.pages, replaced: 0, unknownGuids: 0, match: 'same', warnings: r.warnings, skipped: [] };
  }

  async openBytes(bytes: Uint8Array, name: string): Promise<OpenReport> {
    const rep: OpenReport = { ok: false, pages: 0, own: 0, foreign: 0, existing: false, warnings: [] };
    if (!(bytes[0] === 0x25 && bytes[1] === 0x50 && bytes[2] === 0x44 && bytes[3] === 0x46)) {
      rep.error = `${name || 'The file'} is not a PDF`;
      this.setStatus(rep.error);
      return rep;
    }
    this.busy = true;
    this.setStatus(`Opening ${name || 'PDF'}...`);
    try {
      const sha = await sha256Hex(bytes);
      const have = this.store.docs.find((d) => d.sha256 === sha);
      if (have) {
        rep.ok = true;
        rep.existing = true;
        rep.docId = have.id;
        rep.pages = have.pageCount;
        this.setStatus(`${have.name} is open already`);
        return rep;
      }
      const s = await this.session();
      let pdf: PdfJs.PDFDocumentProxy;
      try {
        pdf = await s.read.openPdf(s.libs, bytes);
      } catch (e) {
        const n = (e as { name?: string }).name ?? '';
        rep.error = n === 'PasswordException' ? `${name} is password protected. Open an unprotected copy.` : `${name || 'The file'} could not be read as a PDF: ${e instanceof Error ? e.message : String(e)}`;
        this.setStatus(rep.error);
        return rep;
      }
      const docId = docIdOf(sha);
      const infos = await s.read.pageInfos(pdf);
      const doc: SheetDoc = { id: docId, name: name || 'drawing.pdf', bytesKey: sha, pageCount: infos.length, sha256: sha, model: this.identity ? { ...this.identity } : null };
      const sheets: Sheet[] = infos.map((p) => ({
        id: sheetIdOf(docId, p.page), docId, page: p.page, name: sheetName(doc.name, p.page, infos.length),
        widthPt: p.widthPt, heightPt: p.heightPt, rotation: p.rotation, box: p.box,
      }));
      // Geo-referencing (ISO 32000 /VP, OGC LGIDict): kept with the sheet, so placing it needs no PDF library later.
      try {
        const geo = await s.read.readGeoPages(s.libs.pdfLib, bytes);
        sheets.forEach((sh, i) => {
          const r = readGeoPage(geo[i] ?? null, boxOf(sh));
          if (r.info) sh.geo = r.info;
        });
      } catch { /* no geo data is fine */ }
      this.proxies.set(docId, Promise.resolve(pdf));
      const persisted = await this.store.putBytes(sha, bytes);
      if (!persisted && !this.store.persistent) rep.warnings.push('This browser does not keep files between visits; the PDF stays for this session only.');
      this.store.docs.push(doc);
      this.store.sheets.push(...sheets);
      for (const sh of sheets.slice(0, MAX_THUMBS)) {
        try { this.store.thumbs.set(sh.id, await this.thumb(sh)); } catch { /* a page that does not render keeps no picture */ }
      }
      // Annotations the PDF already has: ours become editable sketches, the rest one read-only sketch per page.
      try {
        const imp = await this.importAnnotations(s, pdf, bytes, sheets);
        rep.own = imp.own;
        rep.foreign = imp.foreign;
      } catch (e) {
        rep.warnings.push(`The annotations of the PDF could not be read: ${e instanceof Error ? e.message : String(e)}`);
      }
      rep.ok = true;
      rep.docId = docId;
      rep.pages = infos.length;
      const geoPlaced = this.place.autoPlaceAll();
      this.adoptViewpoints();
      this.setStatus(`${doc.name} opened: ${infos.length} sheet${infos.length === 1 ? '' : 's'}${rep.own || rep.foreign ? `, ${rep.own} markup${rep.own === 1 ? '' : 's'} of ours and ${rep.foreign} from others` : ''}${geoPlaced ? `. ${geoPlaced} sheet${geoPlaced === 1 ? '' : 's'} placed in the model from the geo-referencing of the PDF` : ''}`);
      this.scheduleSave();
      return rep;
    } catch (e) {
      rep.error = e instanceof Error ? e.message : String(e);
      this.setStatus(`Could not open the PDF: ${rep.error}`);
      return rep;
    } finally {
      this.busy = false;
      this.emit();
    }
  }

  private async importAnnotations(s: PdfSession, pdf: PdfJs.PDFDocumentProxy, bytes: Uint8Array, sheets: readonly Sheet[]): Promise<{ own: number; foreign: number }> {
    if (!(await s.read.hasMarkupAnnotations(pdf))) return { own: 0, foreign: 0 };
    const { own, lines } = await s.read.readOwn(s.libs.pdfLib, bytes);
    const groups = new Map<string, { sheet: Sheet; title: string; setId: string; items: Array<{ id: string; spec: (typeof own)[number]['spec'] }> }>();
    for (const o of own) {
      const sheet = sheets[o.page - 1];
      const x = o.spec.xray;
      if (!sheet || !x) continue;
      const key = `${o.page}|${x.set}`;
      let g = groups.get(key);
      if (!g) { g = { sheet, title: x.title, setId: x.set, items: [] }; groups.set(key, g); }
      g.items.push({ id: o.spec.name.split('.')[1] ?? newMarkupId(), spec: o.spec });
    }
    let nOwn = 0;
    const now = nowIso();
    for (const g of groups.values()) {
      const markups: Markup[] = [];
      for (const it of g.items) markups.push(...specToMarkups(it.spec, g.sheet, { id: it.id, number: it.spec.xray?.number ?? 0 }));
      if (!markups.length) continue;
      markups.sort((a, b) => a.number - b.number);
      const seen = new Set<number>();
      let hi = Math.max(0, ...markups.map((m) => m.number));
      for (const m of markups) { if (m.number < 1 || seen.has(m.number)) m.number = ++hi; seen.add(m.number); }
      const id = this.markup.get(g.setId) ? newMarkupId('s') : g.setId;
      const set = this.makeSet(g.sheet, uniqueSetTitle(g.title, this.markup.sets), { id, markups, nextNumber: hi + 1 });
      set.created = set.updated = now;
      this.markup.adoptSet(set);
      nOwn += markups.length;
    }
    const ownNumbers = new Set(own.map((o) => o.objectNumber));
    const { annots } = await s.read.readForeign(pdf, ownNumbers, lines);
    let nForeign = 0;
    const perPage = new Map<number, typeof annots>();
    for (const a of annots) { const l = perPage.get(a.page) ?? []; l.push(a); perPage.set(a.page, l); }
    for (const [page, list] of perPage) {
      const sheet = sheets[page - 1];
      if (!sheet) continue;
      const markups: Markup[] = [];
      for (const a of list) for (const m of specToMarkups(a.spec, sheet, { author: 'unknown' })) markups.push(m);
      if (!markups.length) continue;
      markups.forEach((m, i) => { m.number = i + 1; });
      const set = this.makeSet(sheet, uniqueSetTitle(`Imported annotations${sheets.length > 1 ? `, page ${page}` : ''}`, this.markup.sets), { markups, nextNumber: markups.length + 1 });
      set.readonly = true;
      set.note = 'Annotations that were already in the PDF. Read-only.';
      this.markup.adoptSet(set);
      nForeign += markups.length;
    }
    return { own: nOwn, foreign: nForeign };
  }

  // ---------------------------------------------------------------- the PDF documents of a session

  /** The pdf.js document of a doc (opened from the stored bytes on first use, then kept). */
  async proxy(docId: string): Promise<PdfJs.PDFDocumentProxy> {
    let p = this.proxies.get(docId);
    if (!p) {
      const doc = this.store.doc(docId);
      if (!doc) throw new Error('No such PDF');
      p = (async () => {
        const bytes = await this.store.bytesOf(doc);
        if (!bytes) throw new Error(`The bytes of ${doc.name} are not stored (the browser dropped them). Open the PDF again.`);
        const s = await this.session();
        return s.read.openPdf(s.libs, bytes);
      })();
      this.proxies.set(docId, p);
      p.catch(() => this.proxies.delete(docId));
    }
    return p;
  }

  async page(sheet: Sheet): Promise<PdfJs.PDFPageProxy> {
    return (await this.proxy(sheet.docId)).getPage(sheet.page);
  }

  /** Render a sheet to a canvas at `scale` pixels per point (the whole page, or a region in pixels at that scale). */
  async render(sheet: Sheet, canvas: HTMLCanvasElement, scale: number, region?: { x: number; y: number; w: number; h: number }): Promise<{ cancel: () => void; done: Promise<void> }> {
    const mod = await import('./pdfSession');
    const page = await this.page(sheet);
    const r = mod.renderPage({ page, canvas, scale, ...(region ? { region } : {}) });
    return { cancel: r.cancel, done: r.promise };
  }

  private async thumb(sheet: Sheet): Promise<string> {
    const cv = document.createElement('canvas');
    const scale = THUMB_W / Math.max(1, sheet.widthPt);
    const r = await this.render(sheet, cv, scale);
    await r.done;
    return cv.toDataURL('image/jpeg', 0.6);
  }

  // ---------------------------------------------------------------- sketches on sheets

  /** A new empty sketch on a sheet; it becomes the active sketch. */
  newSketch(sheetId: string, title?: string): MarkupSet {
    const sheet = this.store.sheet(sheetId);
    if (!sheet) throw new Error(`No sheet ${sheetId}`);
    const n = this.sketchesOn(sheetId).filter((s) => !s.readonly).length + 1;
    const set = this.makeSet(sheet, uniqueSetTitle(title?.trim() || `${sheet.name} sketch ${n}`, this.markup.sets), {});
    this.markup.adoptSet(set, { activate: true });
    this.markup.setStatus(`Sketch "${set.title}" created on ${sheet.name}`);
    return set;
  }

  private makeSet(sheet: Sheet, title: string, o: { id?: string; markups?: Markup[]; nextNumber?: number }): MarkupSet {
    const now = nowIso();
    const view = sanitizeView(SHEET_VIEW(title)) as SavedView;
    return {
      id: o.id ?? newMarkupId('s'), title, author: this.who, created: now, updated: now, view, camera: SHEET_CAMERA(),
      markups: o.markups ?? [], nextNumber: o.nextNumber ?? 1, model: this.identity ? { ...this.identity } : null, frame: { kind: 'sheet', sheet: sheet.id },
    };
  }

  /** A read-only sketch (imported annotations) copied to an editable one. */
  copyToEditable(setId: string): MarkupSet | null {
    const src = this.markup.get(setId);
    const sheet = src ? this.sheetOfSet(src) : undefined;
    if (!src || !sheet) return null;
    const copy = this.makeSet(sheet, uniqueSetTitle(src.title.replace(/^Imported annotations/, 'Copy of annotations'), this.markup.sets), {
      markups: JSON.parse(JSON.stringify(src.markups)) as Markup[], nextNumber: src.nextNumber,
    });
    for (const m of copy.markups) m.id = newMarkupId();
    this.markup.adoptSet(copy, { activate: true });
    this.markup.setStatus(`"${copy.title}" is an editable copy`);
    return copy;
  }

  /** The editable sketch to draw on in a sheet: the active one when it is on this sheet, else the first, else a new one. */
  sketchToDraw(sheetId: string): MarkupSet {
    const act = this.markup.active;
    if (act && act.frame?.kind === 'sheet' && act.frame.sheet === sheetId && !act.readonly) return act;
    const first = this.sketchesOn(sheetId).find((s) => !s.readonly && this.markup.inScope(s));
    if (first) { this.markup.activeId = first.id; this.markup.selected = null; return first; }
    return this.newSketch(sheetId);
  }

  async removeDoc(docId: string): Promise<void> {
    const sheets = this.sheetsOf(docId);
    for (const sh of sheets) {
      for (const set of this.sketchesOn(sh.id)) this.markup.deleteSet(set.id);
      if (this.openId === sh.id) this.close();
      this.shown3d.delete(sh.id);
      this.overlayOn.delete(sh.id);
      if (this.placeId === sh.id) this.closePlace();
    }
    this.proxies.get(docId)?.then((p) => p.destroy()).catch(() => undefined);
    this.proxies.delete(docId);
    await this.store.removeDoc(docId);
    this.scheduleSave();
    this.setStatus('PDF removed');
  }

  // ---------------------------------------------------------------- the viewer

  /** Open a sheet in the viewer. */
  open(sheetId: string): boolean {
    const sh = this.store.sheet(sheetId);
    if (!sh) return false;
    this.openId = sheetId;
    this.app.renderPaused = true; // the 3D scene is under the sheet: it is not drawn meanwhile
    this.showViewer?.(sheetId);
    this.emit();
    return true;
  }
  /** Back to the 3D view. */
  close(): void {
    if (this.openId === null) return;
    this.openId = null;
    this.app.renderPaused = false;
    this.app.renderer.markDirty();
    this.markup.setEditing(false);
    this.showViewer?.(null);
    this.emit();
  }
  /** The sheet of a sketch, opened (the sketch becomes active). False when its PDF is not open. */
  openSet(set: MarkupSet): boolean {
    const sh = this.sheetOfSet(set);
    if (!sh) return false;
    this.markup.activeId = set.id;
    this.markup.selected = null;
    return this.open(sh.id);
  }

  onModel(): void {
    // Sheets belong to the model they were opened on: the viewer closes when the model changes; other models' sheets are hidden.
    if (this.openId) this.close();
    if (this.placeId) this.closePlace();
    this.shown3d.clear();
    this.overlayOn.clear();
    this.place.geoNotes.clear();
    this.place.autoPlaceAll();
    this.emit();
  }

  // ---------------------------------------------------------------- placement, 3D, overlay

  /** A sheet was placed, placed anew or lost its placement: save, redraw, tell the panel. */
  placementChanged(sheet: Sheet): void {
    this.scheduleSave();
    this.markup.emit(true);
    this.setStatus(sheet.placement ? `${sheet.name}: ${placementWords(sheet)}` : `${sheet.name}: placement removed`);
  }

  /** A shape or text was drawn or moved on the sheet: attach it to the model elements under it (placed sheets only). */
  attachNew(set: MarkupSet, m: Markup): void {
    if (this.place.attachMarkup(set, m)) this.markup.emit(true);
  }

  openPlace(sheetId: string): boolean {
    if (!this.store.sheet(sheetId) || !this.place.loaded) return false;
    this.placeId = sheetId;
    this.app.renderPaused = true;
    this.showPlace?.(sheetId);
    this.emit();
    return true;
  }
  closePlace(): void {
    if (this.placeId === null) return;
    this.placeId = null;
    if (this.openId === null) { this.app.renderPaused = false; this.app.renderer.markDirty(); }
    this.showPlace?.(null);
    this.emit();
  }

  /** Opacity of every sheet quad in 3D (the quads follow without the panel being rebuilt). */
  setQuadOpacity(v: number): void {
    this.quadOpacity = Math.max(0.05, Math.min(1, v));
    this.quadOpacityChanged?.();
  }
  /** Set by the 3D scene: redraw the quads. */
  quadOpacityChanged: (() => void) | null = null;

  setShow3d(sheetId: string, on: boolean): void {
    if (on && this.store.sheet(sheetId)?.placement) this.shown3d.add(sheetId);
    else this.shown3d.delete(sheetId);
    this.emit();
  }
  setOverlay(sheetId: string, on: boolean): void {
    if (on && this.store.sheet(sheetId)?.placement) this.overlayOn.add(sheetId);
    else this.overlayOn.delete(sheetId);
    this.emit();
  }

  // ---------------------------------------------------------------- export: a marked-up copy of the PDF

  /** The editable sketches of every page of a doc, as the writer takes them. */
  private pagesToWrite(docId: string): Array<{ sheet: Sheet; sets: MarkupSet[] }> {
    return this.sheetsOf(docId).map((sheet) => ({ sheet, sets: this.sketchesOn(sheet.id).filter((s) => !s.readonly && this.markup.inScope(s)) }));
  }

  async exportMarkedUp(docId: string): Promise<ExportedFile & { added: number; removed: number; subtypes: Record<string, number> }> {
    const doc = this.store.doc(docId);
    if (!doc) throw new Error('No such PDF');
    const bytes = await this.store.bytesOf(doc);
    if (!bytes) throw new Error(`The bytes of ${doc.name} are not stored. Open the PDF again.`);
    const s = await this.session();
    const r = await s.write.writeMarkedUp(s.libs.pdfLib, bytes, this.pagesToWrite(docId));
    const name = `${slug(doc.name.replace(/\.pdf$/i, ''))}-markup.pdf`;
    this.setStatus(`Marked-up PDF: ${r.added} annotation${r.added === 1 ? '' : 's'} on the layer "X-ray markups"${r.removed ? `, ${r.removed} of the last export replaced` : ''}`);
    return { name, bytes: r.bytes, added: r.added, removed: r.removed, subtypes: r.subtypes };
  }

  async downloadMarkedUp(docId: string): Promise<ExportedFile> {
    const f = await this.exportMarkedUp(docId);
    download(f.name, f.bytes, 'application/pdf');
    return f;
  }

  // ---------------------------------------------------------------- persistence

  private scheduleSave(): void {
    if (this.saveTimer) return;
    this.saveTimer = setTimeout(() => {
      this.saveTimer = null;
      void this.save();
    }, 400);
  }

  async save(): Promise<void> {
    const sets = this.sheetSets();
    const sig = JSON.stringify([sets, this.store.docs.length, this.store.sheets.length, this.store.sheets.map((x) => [x.placement, x.geo])]);
    if (sig === this.lastSaved) return;
    this.lastSaved = sig;
    await this.store.saveMeta(sets);
  }

  // ---------------------------------------------------------------- raise as issue (BCF)

  /** The region of a sheet a snapshot shows: the markups with a margin, at least a quarter of the page; the whole page when empty. */
  snapshotRegion(set: MarkupSet, sheet: Sheet): [number, number, number, number] {
    const W = sheet.widthPt;
    const H = sheet.heightPt;
    const flat: number[] = [];
    for (const m of set.markups) {
      if (m.shape) for (const p of m.shape.points) flat.push(...userToDisplay(sheet, p[0], p[1]));
      else if (m.anchor) flat.push(...userToDisplay(sheet, m.anchor.point[0], m.anchor.point[1]));
    }
    if (flat.length < 2) return [0, 0, W, H];
    const b = ptsBounds(flat);
    const mx = Math.max(40 * sheetUnit(sheet), (b.x1 - b.x0) * 0.25);
    const my = Math.max(40 * sheetUnit(sheet), (b.y1 - b.y0) * 0.25);
    let x0 = Math.max(0, b.x0 - mx);
    let x1 = Math.min(W, b.x1 + mx);
    let y0 = Math.max(0, b.y0 - my);
    let y1 = Math.min(H, b.y1 + my);
    const minW = W * 0.25;
    const minH = H * 0.25;
    if (x1 - x0 < minW) { const c = (x0 + x1) / 2; x0 = Math.max(0, Math.min(W - minW, c - minW / 2)); x1 = x0 + minW; }
    if (y1 - y0 < minH) { const c = (y0 + y1) / 2; y0 = Math.max(0, Math.min(H - minH, c - minH / 2)); y1 = y0 + minH; }
    return [x0, y0, x1, y1];
  }

  /** A PNG of the region of the sheet (displayed points) with the sketch drawn on it. */
  async snapshot(set: MarkupSet, sheet: Sheet, region: [number, number, number, number]): Promise<Uint8Array> {
    const rw = region[2] - region[0];
    const rh = region[3] - region[1];
    const scale = Math.min(SNAP_MAX / Math.max(rw, rh), 8);
    const cv = document.createElement('canvas');
    const r = await this.render(sheet, cv, scale, { x: region[0] * scale, y: region[1] * scale, w: rw * scale, h: rh * scale });
    await r.done;
    const g = cv.getContext('2d')!;
    g.save();
    g.translate(-region[0] * scale, -region[1] * scale);
    for (const m of set.markups) drawOps(g as unknown as Ctx2D, layoutSheetMarkup(m, sheet, { scale }).ops);
    g.restore();
    const blob = await new Promise<Blob | null>((res) => cv.toBlob(res, 'image/png'));
    if (!blob) throw new Error('The snapshot could not be made');
    return new Uint8Array(await blob.arrayBuffer());
  }

  private sheetRef(set: MarkupSet, sheet: Sheet, doc: SheetDoc, region: [number, number, number, number]): BcfSheetRef {
    // The region is stored in user space (what the PDF is made of), two opposite corners.
    return {
      sha256: doc.sha256, page: sheet.page, name: sheet.name, docName: doc.name, title: set.title,
      bounds: [region[0], region[1], region[2], region[3]], markups: JSON.parse(JSON.stringify(set.markups)) as Markup[],
    };
  }

  /**
   * Raise a sheet sketch as an issue: a new one or, with `topic`, one more viewpoint of an existing issue. The viewpoint holds a
   * snapshot image of the sheet region, the topic a DocumentReference to the PDF, and the side file names the sheet, page and the
   * bounds of the shapes. The viewpoint links to the sketch by id (src/issues/link.ts), like a 3D sketch.
   */
  async raise(setId: string, o: { topic?: string } = {}): Promise<string> {
    const bcf = this.bcf;
    if (!bcf) throw new Error('The BCF tool is not available in this build');
    const set = this.markup.get(setId);
    if (!set || !isSheetSet(set)) throw new Error(`No sheet sketch ${setId}`);
    const sheet = this.sheetOfSet(set);
    const doc = sheet ? this.store.doc(sheet.docId) : undefined;
    if (!sheet || !doc) throw new Error('The PDF of this sketch is not open');
    const bytes = await this.store.bytesOf(doc);
    if (!bytes) throw new Error(`The bytes of ${doc.name} are not stored. Open the PDF again.`);
    const region = this.snapshotRegion(set, sheet);
    const png = await this.snapshot(set, sheet, region);
    const guid = newGuid();
    // A placed sheet with a sketch attached to the model gets a real 3D viewpoint too: the target elements as components and a camera that frames them.
    const vp = this.place.viewpointFor(set);
    const ref: BcfViewpointRef = { guid, data: vp ? { ...vp, guid } : null, snapshot: png, snapshotMime: 'image/png', sheet: this.sheetRef(set, sheet, doc, region), sketchId: set.id };
    const author = this.who;
    const topic: BcfTopic = o.topic
      ? bcf.addSheetViewpoint(o.topic, ref, { filename: doc.name, data: bytes, sha256: doc.sha256 })
      : bcf.createSheetTopic({ title: set.title, description: set.note ?? `Sketch "${set.title}" on ${sheet.name}.`, author }, ref, { filename: doc.name, data: bytes, sha256: doc.sha256 });
    set.issue = { topic: topic.guid, viewpoint: ref.guid };
    this.markup.emit();
    this.markup.setStatus(`Sketch "${set.title}" raised as the issue "${topic.title}"`);
    return topic.guid;
  }

  /** Before a BCF export: the snapshot and the shapes of every sheet viewpoint follow the sketch as it is now. */
  async refreshIssueViewpoints(): Promise<void> {
    if (!this.bcf) return;
    for (const t of this.bcf.topics) {
      for (const v of t.viewpoints) {
        if (!v.sheet) continue;
        const set = v.sketchId ? this.markup.get(v.sketchId) : undefined;
        const sheet = set ? this.sheetOfSet(set) : undefined;
        const doc = sheet ? this.store.doc(sheet.docId) : undefined;
        if (!set || !sheet || !doc) continue;
        const sig = JSON.stringify(set.markups);
        if (JSON.stringify(v.sheet.markups) === sig && v.snapshot) continue;
        const region = this.snapshotRegion(set, sheet);
        try {
          v.snapshot = await this.snapshot(set, sheet, region);
          v.snapshotMime = 'image/png';
        } catch { /* the earlier snapshot stays */ }
        v.sheet = this.sheetRef(set, sheet, doc, region);
        const vp = this.place.viewpointFor(set);
        if (vp) v.data = { ...vp, guid: v.data?.guid ?? v.guid };
        else if (v.data && !sheet.placement) v.data = null;
        this.bcf.touch(t);
      }
    }
  }

  /**
   * Opened BCF topics with sheet viewpoints: each becomes a sketch on its sheet, linked to its issue. The sheet is found by the
   * SHA-256 of the PDF (the ids derive from it); a PDF that came inside the bcfzip is opened from there.
   */
  adoptViewpoints(): number {
    const bcf = this.bcf;
    if (!bcf || this.adopting) return 0;
    this.adopting = true;
    let n = 0;
    try {
      for (const t of bcf.topics) {
        for (const v of t.viewpoints) {
          const ref = v.sheet;
          if (!ref || v.sketchId) continue;
          const docId = docIdOf(ref.sha256);
          const sheet = this.store.sheet(sheetIdOf(docId, ref.page));
          // A sketch of this viewpoint made earlier (an issue opened twice) is linked again.
          const mk = (ref.markups ?? []).map((m) => JSON.parse(JSON.stringify(m)) as Markup);
          const id = newMarkupId('s');
          const set: MarkupSet = {
            id, title: uniqueSetTitle(ref.title || `${t.title}`, this.markup.sets), author: t.creationAuthor || 'unknown', created: nowIso(), updated: nowIso(),
            view: sanitizeView(SHEET_VIEW(ref.title || t.title)) as SavedView, camera: SHEET_CAMERA(), markups: mk,
            nextNumber: Math.max(1, ...mk.map((m) => m.number + 1)), model: t.model ? { ...t.model } : null,
            frame: { kind: 'sheet', sheet: sheet?.id ?? sheetIdOf(docId, ref.page) }, issue: { topic: t.guid, viewpoint: v.guid },
          };
          this.markup.adoptSet(set);
          v.sketchId = id;
          n++;
        }
      }
    } finally {
      this.adopting = false;
    }
    if (n) this.emit();
    return n;
  }

  /** PDFs that came inside an opened BCF file and are not open yet: opened now (their sketches then find their sheets). */
  async openBcfDocuments(): Promise<number> {
    const bcf = this.bcf;
    if (!bcf) return 0;
    let n = 0;
    for (const d of bcf.project.documents) {
      if (!d.data || this.seenDocs.has(d.data) || !/\.pdf$/i.test(d.filename) || !(d.data[0] === 0x25 && d.data[1] === 0x50)) continue;
      this.seenDocs.add(d.data);
      const sha = await sha256Hex(d.data);
      if (this.store.docs.some((x) => x.sha256 === sha)) continue;
      const r = await this.openBytes(d.data, d.filename);
      if (r.ok) n++;
    }
    return n;
  }

  /** The doc of a sheet id that came from a file (sketch frames and BCF refs name sheets this way). */
  hasSheet(sheetId: string): boolean {
    return !!parseSheetId(sheetId) && !!this.store.sheet(sheetId);
  }
}
