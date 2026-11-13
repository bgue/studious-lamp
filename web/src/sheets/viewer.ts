// The sheet viewer: a 2D view of a PDF page that covers the 3D canvas area while it is open (the 3D view stays loaded under it).
// Pan and zoom with mouse, wheel and touch pinch. The page is drawn by pdf.js: a whole-page picture that scales with the zoom, and
// once the zoom settles a sharp picture of the visible part at the real zoom level. Sketches are drawn on top as SVG from the same
// layout as the 3D view and the export (layout.ts). The floating drawing toolbar is the markup toolbar (src/markup/toolbar.ts) with
// the 3D-only tools left out. Shapes are stored in PDF user-space points, so they stay on the same place under pan and zoom.

import { renderOps } from '../bcf/pins';
import { svgEl } from '../ui/overlay';
import { TOOLS, toolInfo } from '../markup/controller';
import type { ToolId } from '../markup/controller';
import { distToPolyline, pointInPolygon, simplify } from '../markup/geometry';
import { DrawToolbar } from '../markup/toolbar';
import { isAnchorKind, newMarkup } from '../markup/model';
import type { Markup, MarkupSet } from '../markup/model';
import { el } from '../ui/dom';
import { STATUS_H } from '../ui/statusBar';
import { STRIP_W } from '../ui/toolbarView';
import { TOPBAR_H } from '../ui/topBar';
import type { SheetsController } from './controller';
import { layoutSheetMarkup, nextOffset } from './layout';
import type { MarkupLayout } from '../markup/layout';
import { displayToUser, userToDisplay } from './model';
import type { Sheet } from './model';
import { fitToChrome } from './chrome';
import { drawCut, modelToPixels } from './overlayDraw';
import { mm } from './placement';
import { isPlan, placementStatus } from './placement';

const STYLE_ID = 'sheet-view-styles';
const CSS = `
#sheet-view{position:absolute;left:${STRIP_W}px;right:0;top:${TOPBAR_H}px;bottom:${STATUS_H}px;z-index:13;display:none;flex-direction:column;background:#252a32;color:#dfe6ee;font:12px/1.35 system-ui,sans-serif}
#sheet-view.on{display:flex}
#sheet-view *{box-sizing:border-box}
#sheet-view .sv-bar{flex:0 0 auto;display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:5px 8px;background:#141820;border-bottom:1px solid #262d3a}
#sheet-view .sv-bar button,#sheet-view .sv-bar select{background:#1c2f45;color:#eaf2ff;border:1px solid #3b6c9c;border-radius:8px;font:inherit;min-height:32px;padding:0 10px;cursor:pointer}
#sheet-view .sv-bar button:disabled{opacity:.4;cursor:default}
#sheet-view .sv-bar button[aria-pressed=true]{background:#1f4a7a;border-color:#3b9cff}
#sheet-view .sv-bar .sv-back{background:#1f6fe5;border-color:#3b9cff;font-weight:700}
#sheet-view .sv-title{flex:1 1 120px;min-width:0;font-weight:700;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#sheet-view .sv-pager{display:flex;align-items:center;gap:4px}
#sheet-view .sv-pager button{min-width:32px;padding:0}
#sheet-view .sv-sel{max-width:180px}
#sheet-view .sv-stage{position:relative;flex:1 1 auto;min-height:0;overflow:hidden;touch-action:none;cursor:grab;background:#3a404a}
#sheet-view .sv-stage.drawing{cursor:crosshair}
#sheet-view .sv-stage.panning{cursor:grabbing}
#sheet-view canvas{position:absolute;left:0;top:0;transform-origin:0 0;background:#fff;box-shadow:0 2px 14px rgba(0,0,0,.5);image-rendering:auto}
#sheet-view canvas.sv-detail{box-shadow:none;display:none}
#sheet-view canvas.sv-ovl{background:transparent;box-shadow:none;pointer-events:none}
#sheet-view .sv-bar2{padding:3px 8px;font-size:12px}
#sheet-view .sv-bar2 .sv-pstat{flex:1 1 140px;min-width:0;color:#9fc4ee;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#sheet-view .sv-opac{width:90px;min-width:60px}
#sheet-view .sv-mis{color:#ffd27a;white-space:nowrap}
#sheet-view svg.sv-marks{position:absolute;left:0;top:0;width:100%;height:100%;overflow:visible;pointer-events:none}
#sheet-view .sv-msg{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);padding:8px 12px;border-radius:8px;background:rgba(20,24,32,.92);color:#eaf2ff;max-width:80%;text-align:center}
#sheet-view .sv-info{position:absolute;left:8px;bottom:8px;max-width:min(420px,calc(100% - 16px));padding:6px 9px;border-radius:8px;background:rgba(20,24,32,.94);border:1px solid #3b6c9c;color:#eaf2ff;display:none}
#sheet-view .sv-info b{color:#9fc4ee}
#sheet-view .sv-zoom{position:absolute;right:8px;top:8px;display:flex;flex-direction:column;gap:4px}
#sheet-view .sv-zoom button{width:34px;height:34px;border-radius:8px;border:1px solid #3b6c9c;background:rgba(20,32,46,.94);color:#eaf2ff;font:700 16px system-ui,sans-serif;cursor:pointer}
@media (max-width:700px){#sheet-view .sv-bar{padding:4px 6px;gap:4px}#sheet-view .sv-sel{max-width:130px}}
`;

const CLICK_SLOP = 5;
const HIT_PX = 14;

interface Stroke { tool: ToolId; pts: Array<[number, number]>; id: number }

function isEditable(t: EventTarget | null): boolean {
  const e = t as HTMLElement | null;
  return !!e && !!e.tagName && (e.tagName === 'INPUT' || e.tagName === 'TEXTAREA' || e.tagName === 'SELECT' || e.isContentEditable);
}

/** The tools the sheet viewer offers: every drawing tool that means something on a flat page (not the 3D pointer). */
export function sheetTools(): typeof TOOLS {
  return TOOLS.filter((t) => t.id !== 'pointer');
}

export class SheetViewer {
  readonly root: HTMLDivElement;
  private readonly stage: HTMLDivElement;
  private readonly base: HTMLCanvasElement;
  private readonly detail: HTMLCanvasElement;
  private readonly svg: SVGSVGElement;
  private readonly layer: SVGGElement;
  private readonly msg: HTMLDivElement;
  private readonly info: HTMLDivElement;
  private readonly title: HTMLDivElement;
  private readonly pageLbl: HTMLSpanElement;
  private readonly sketchSel: HTMLSelectElement;
  private readonly drawBtn: HTMLButtonElement;
  private readonly ovl: HTMLCanvasElement;
  private readonly pstat: HTMLSpanElement;
  private readonly placeBtn: HTMLButtonElement;
  private readonly ovlBtn: HTMLButtonElement;
  private readonly opac: HTMLInputElement;
  private readonly misfit: HTMLSpanElement;
  private readonly prevBtn: HTMLButtonElement;
  private readonly nextBtn: HTMLButtonElement;
  private bar: DrawToolbar | null = null;
  sheet: Sheet | null = null;
  /** Pixels per point and the page's top left corner in stage pixels. */
  scale = 1;
  tx = 0;
  ty = 0;
  private baseScale = 1;
  private detailScale = 0;
  private detailTimer: ReturnType<typeof setTimeout> | null = null;
  private detailTask: { cancel: () => void } | null = null;
  private gen = 0;
  private frame = 0;
  private stroke: Stroke | null = null;
  private poly: { tool: ToolId; pts: Array<[number, number]>; at: number } | null = null;
  private last: [number, number] | null = null;
  private readonly pointers = new Map<number, [number, number]>();
  private gesture: { d: number; cx: number; cy: number } | null = null;
  private pan: { x: number; y: number; tx: number; ty: number; id: number; moved: boolean } | null = null;
  private drag: { id: string; sx: number; sy: number; kind: 'shape' | 'box'; from: Array<[number, number]>; off: [number, number]; moved: boolean } | null = null;
  private hits = new Map<string, MarkupLayout['hit']>();
  /** Counts for the smoke test and scripts. */
  renders = { base: 0, detail: 0 };
  /** How many element outlines the model overlay drew last (tests). */
  overlayDrawn = 0;

  constructor(private readonly ctl: SheetsController, host: HTMLElement) {
    if (!document.getElementById(STYLE_ID)) {
      const st = document.createElement('style');
      st.id = STYLE_ID;
      st.textContent = CSS;
      document.head.appendChild(st);
    }
    const root = el('div', '', { id: 'sheet-view', role: 'region', 'aria-label': 'Sheet view', 'data-help-key': 'Sheet view' });
    const bar = el('div', 'sv-bar');
    const back = el('button', 'sv-back', { type: 'button', 'data-act': 'back', title: 'Close the sheet and return to the 3D model', 'data-help-key': 'Sheet view/Back to model' }, 'Back to model');
    back.addEventListener('click', () => ctl.close());
    this.title = el('div', 'sv-title', { 'data-sv': 'title' });
    const pager = el('div', 'sv-pager');
    this.prevBtn = el('button', '', { type: 'button', 'data-act': 'prev', 'aria-label': 'Previous page', title: 'Previous page' }, '‹');
    this.nextBtn = el('button', '', { type: 'button', 'data-act': 'next', 'aria-label': 'Next page', title: 'Next page' }, '›');
    this.pageLbl = el('span', '', { 'data-sv': 'page' });
    this.prevBtn.addEventListener('click', () => this.turn(-1));
    this.nextBtn.addEventListener('click', () => this.turn(1));
    pager.append(this.prevBtn, this.pageLbl, this.nextBtn);
    const fit = el('button', '', { type: 'button', 'data-act': 'fit', title: 'Fit the page in the window', 'data-help-key': 'Sheet view/Fit' }, 'Fit');
    fit.addEventListener('click', () => this.fit());
    this.sketchSel = el('select', 'sv-sel', { 'aria-label': 'Sketch on this sheet', 'data-sv': 'sketch', title: 'The sketch you draw on', 'data-help-key': 'Sheet view/Sketch' });
    this.sketchSel.addEventListener('change', () => {
      const id = this.sketchSel.value;
      if (id === '__new') { if (this.sheet) { ctl.newSketch(this.sheet.id); ctl.markup.setEditing(true); } return; }
      ctl.markup.activeId = id || null;
      ctl.markup.selected = null;
      ctl.markup.emit();
    });
    this.drawBtn = el('button', '', { type: 'button', 'data-act': 'draw', 'aria-pressed': 'false', title: 'Show the drawing tools and draw on this sheet', 'data-help-key': 'Sheet view/Draw' }, 'Draw');
    this.drawBtn.addEventListener('click', () => {
      if (!this.sheet) return;
      if (ctl.markup.editing) { ctl.markup.setEditing(false); return; }
      ctl.sketchToDraw(this.sheet.id);
      ctl.markup.setEditing(true);
    });
    bar.append(back, this.title, pager, fit, this.sketchSel, this.drawBtn);
    // Second row: where the sheet is in the model, and the overlay of the model on it.
    const bar2 = el('div', 'sv-bar sv-bar2', { 'data-sv': 'placebar' });
    this.pstat = el('span', 'sv-pstat', { 'data-sv': 'placement' });
    this.placeBtn = el('button', '', { type: 'button', 'data-act': 'place', title: 'Place this sheet in the model: pick two points on the sheet and the same two in the model', 'data-help-key': 'Sheet view/Place in model' }, 'Place in model…');
    this.placeBtn.addEventListener('click', () => { if (this.sheet) ctl.openPlace(this.sheet.id); });
    this.ovlBtn = el('button', '', { type: 'button', 'data-act': 'overlay', 'aria-pressed': 'false', title: 'Draw the model as thin outlines over the sheet: the plan cut about 1.2 m above the level, lined up through the placement', 'data-help-key': 'Sheet view/Model overlay' }, 'Model overlay');
    this.ovlBtn.addEventListener('click', () => { if (this.sheet) ctl.setOverlay(this.sheet.id, !ctl.overlayOn.has(this.sheet.id)); });
    this.opac = el('input', 'sv-opac', { type: 'range', min: '10', max: '100', step: '5', 'data-sv': 'opacity', 'aria-label': 'Overlay opacity', title: 'Opacity of the model overlay', 'data-help-key': 'Sheet view/Overlay opacity' }) as HTMLInputElement;
    this.opac.addEventListener('input', () => { ctl.overlayOpacity = Number(this.opac.value) / 100; this.invalidate(); });
    this.misfit = el('span', 'sv-mis', { 'data-sv': 'misfit', title: 'How far the points you picked are from where the fitted placement puts them (root mean square, millimetres of the model)' });
    bar2.append(this.pstat, this.placeBtn, this.ovlBtn, this.opac, this.misfit);
    this.stage = el('div', 'sv-stage', { 'data-sv': 'stage' });
    this.base = el('canvas', 'sv-base', { 'data-sv': 'base' });
    this.detail = el('canvas', 'sv-detail', { 'data-sv': 'detail' });
    this.ovl = el('canvas', 'sv-ovl', { 'data-sv': 'overlay' });
    this.svg = svgEl('svg', { class: 'sv-marks', 'data-sv': 'marks' }) as SVGSVGElement;
    this.layer = svgEl('g', {}) as SVGGElement;
    this.svg.appendChild(this.layer);
    this.msg = el('div', 'sv-msg', { role: 'status', 'data-sv': 'msg' });
    this.msg.style.display = 'none';
    this.info = el('div', 'sv-info', { 'data-sv': 'info', role: 'status' });
    const zoom = el('div', 'sv-zoom');
    const zin = el('button', '', { type: 'button', 'aria-label': 'Zoom in', title: 'Zoom in', 'data-act': 'zoom-in' }, '+');
    const zout = el('button', '', { type: 'button', 'aria-label': 'Zoom out', title: 'Zoom out', 'data-act': 'zoom-out' }, '−');
    zin.addEventListener('click', () => this.zoomAt(this.stage.clientWidth / 2, this.stage.clientHeight / 2, 1.5));
    zout.addEventListener('click', () => this.zoomAt(this.stage.clientWidth / 2, this.stage.clientHeight / 2, 1 / 1.5));
    zoom.append(zin, zout);
    this.stage.append(this.base, this.detail, this.ovl, this.svg, zoom, this.msg, this.info);
    root.append(bar, bar2, this.stage);
    host.appendChild(root);
    this.root = root;
    // The drawing toolbar is the markup one, in this viewer's own area.
    this.bar = new DrawToolbar(ctl.markup, root, { id: 'sheet-float', frame: () => this.stage, tools: sheetTools });
    this.bar.root.setAttribute('data-help-key', 'Sheet view/Drawing toolbar');

    const st = this.stage;
    st.addEventListener('pointerdown', (e) => this.onDown(e));
    st.addEventListener('pointermove', (e) => this.onMove(e));
    st.addEventListener('pointerup', (e) => this.onUp(e));
    st.addEventListener('pointercancel', (e) => this.onUp(e));
    st.addEventListener('wheel', (e) => {
      e.preventDefault();
      const r = st.getBoundingClientRect();
      const k = Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0018));
      this.zoomAt(e.clientX - r.left, e.clientY - r.top, k);
    }, { passive: false });
    st.addEventListener('dblclick', (e) => { if (this.poly) { e.preventDefault(); this.finishPoly(); } });
    st.addEventListener('contextmenu', (e) => e.preventDefault());
    window.addEventListener('keydown', (e) => this.onKey(e), true);
    new ResizeObserver(() => { if (this.sheet) this.invalidate(); }).observe(st);
    ctl.onChange(() => { if (this.sheet) this.invalidate(); });
    let lastTool: ToolId = ctl.markup.tool;
    let lastEditing = ctl.markup.editing;
    ctl.markup.onChange(() => {
      // Another tool, or Done: a drawing in progress is dropped.
      if (ctl.markup.tool !== lastTool || ctl.markup.editing !== lastEditing) this.cancel(true);
      lastTool = ctl.markup.tool;
      lastEditing = ctl.markup.editing;
      this.invalidate();
    });
  }

  get visible(): boolean {
    return this.root.classList.contains('on');
  }

  // ---------------------------------------------------------------- showing a sheet

  async show(sheetId: string | null): Promise<void> {
    if (sheetId === null) {
      this.root.classList.remove('on');
      document.body.classList.remove('sheet-open');
      this.cancel(true);
      this.sheet = null;
      this.bar?.update(false, null, 0, () => undefined);
      this.gen++;
      return;
    }
    const sh = this.ctl.store.sheet(sheetId);
    if (!sh) return;
    const changed = this.sheet?.id !== sh.id;
    this.root.classList.add('on');
    document.body.classList.add('sheet-open');
    this.sheet = sh;
    this.cancel(true);
    if (changed) {
      this.setMsg('Loading the sheet...');
      this.detail.style.display = 'none';
      this.detailScale = 0;
      this.ctl.markup.selected = null;
      const act = this.ctl.markup.active;
      if (!act || act.frame?.kind !== 'sheet' || act.frame.sheet !== sh.id) {
        const first = this.ctl.sketchesOn(sh.id).find((s) => this.ctl.markup.inScope(s));
        this.ctl.markup.activeId = first?.id ?? null;
      }
      const gen = ++this.gen;
      this.baseScale = Math.min(3, 2400 / Math.max(sh.widthPt, sh.heightPt));
      try {
        const r = await this.ctl.render(sh, this.base, this.baseScale);
        await r.done;
        if (gen !== this.gen) return;
        this.renders.base++;
        this.setMsg('');
      } catch (e) {
        if (gen !== this.gen) return;
        this.setMsg(`The sheet could not be drawn: ${e instanceof Error ? e.message : String(e)}`);
      }
      this.fit();
    }
    this.invalidate();
  }

  private setMsg(t: string): void {
    this.msg.textContent = t;
    this.msg.style.display = t ? '' : 'none';
  }

  private turn(d: number): void {
    const sh = this.sheet;
    if (!sh) return;
    const pages = this.ctl.sheetsOf(sh.docId);
    const i = pages.findIndex((p) => p.id === sh.id) + d;
    const next = pages[i];
    if (next) this.ctl.open(next.id);
  }

  // ---------------------------------------------------------------- view transform

  fit(): void {
    const sh = this.sheet;
    if (!sh) return;
    const W = this.stage.clientWidth;
    const H = this.stage.clientHeight;
    const m = 10;
    this.scale = Math.max(0.02, Math.min((W - 2 * m) / sh.widthPt, (H - 2 * m) / sh.heightPt));
    this.tx = (W - sh.widthPt * this.scale) / 2;
    this.ty = (H - sh.heightPt * this.scale) / 2;
    this.moved();
  }

  /** Zoom by `k` about a stage point. */
  zoomAt(x: number, y: number, k: number): void {
    const sh = this.sheet;
    if (!sh) return;
    const min = Math.min(this.stage.clientWidth / sh.widthPt, this.stage.clientHeight / sh.heightPt) * 0.2;
    const max = 40;
    const s = Math.max(min, Math.min(max, this.scale * k));
    const f = s / this.scale;
    this.tx = x - (x - this.tx) * f;
    this.ty = y - (y - this.ty) * f;
    this.scale = s;
    this.moved();
  }

  /** The view moved: redraw now, and draw the sharp picture once it settles. */
  private moved(): void {
    this.detail.style.display = 'none';
    this.detailScale = 0;
    this.invalidate();
    if (this.detailTimer) clearTimeout(this.detailTimer);
    this.detailTimer = setTimeout(() => void this.sharpen(), 220);
  }

  private async sharpen(): Promise<void> {
    const sh = this.sheet;
    if (!sh || !this.visible) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const want = this.scale * dpr;
    if (want <= this.baseScale * 0.95) return; // the whole-page picture is sharp enough
    this.detailTask?.cancel();
    const gen = ++this.gen;
    // The visible part of the page, in pixels at the render scale from the page's top left.
    const W = this.stage.clientWidth;
    const H = this.stage.clientHeight;
    const x0 = Math.max(0, -this.tx);
    const y0 = Math.max(0, -this.ty);
    const x1 = Math.min(sh.widthPt * this.scale, W - this.tx);
    const y1 = Math.min(sh.heightPt * this.scale, H - this.ty);
    if (x1 - x0 < 2 || y1 - y0 < 2) return;
    const k = want / this.scale;
    const region = { x: x0 * k, y: y0 * k, w: (x1 - x0) * k, h: (y1 - y0) * k };
    const cv = document.createElement('canvas');
    try {
      const r = await this.ctl.render(sh, cv, want, region);
      this.detailTask = r;
      await r.done;
    } catch {
      return; // cancelled by the next move
    }
    if (gen !== this.gen || !this.visible || this.sheet?.id !== sh.id) return;
    // Swap the new picture in (the old one is not blanked first).
    this.detail.width = cv.width;
    this.detail.height = cv.height;
    this.detail.getContext('2d')!.drawImage(cv, 0, 0);
    this.detail.style.width = `${x1 - x0}px`;
    this.detail.style.height = `${y1 - y0}px`;
    this.detail.style.transform = `translate(${this.tx + x0}px, ${this.ty + y0}px)`;
    this.detail.style.display = 'block';
    this.detailScale = want;
    this.renders.detail++;
  }

  // ---------------------------------------------------------------- coordinates

  private rel(e: PointerEvent | MouseEvent): [number, number] {
    const r = this.stage.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  }
  /** Stage pixels to displayed-page points. */
  toPage(x: number, y: number): [number, number] {
    return [(x - this.tx) / this.scale, (y - this.ty) / this.scale];
  }
  /** Stage pixels to PDF user-space points. */
  toUser(x: number, y: number): [number, number] {
    const [px, py] = this.toPage(x, y);
    return displayToUser(this.sheet!, px, py);
  }
  /** PDF user-space points to stage pixels. */
  toStage(ux: number, uy: number): [number, number] {
    const [dx, dy] = userToDisplay(this.sheet!, ux, uy);
    return [this.tx + dx * this.scale, this.ty + dy * this.scale];
  }

  // ---------------------------------------------------------------- the sketch being drawn on

  private get set(): MarkupSet | null {
    const s = this.ctl.markup.active;
    return s && this.sheet && s.frame?.kind === 'sheet' && s.frame.sheet === this.sheet.id ? s : null;
  }
  private get tool(): ToolId {
    return this.ctl.markup.tool;
  }
  /** The viewer takes drawing input: editing, with a drawing tool, on an editable sketch of this sheet. */
  private get drawingTool(): boolean {
    const c = this.ctl.markup;
    return c.editing && c.tool !== 'select' && !!this.set && !this.set.readonly;
  }

  // ---------------------------------------------------------------- pointer input

  private onDown(e: PointerEvent): void {
    if (!this.sheet) return;
    this.stage.setPointerCapture?.(e.pointerId);
    const p = this.rel(e);
    this.pointers.set(e.pointerId, p);
    if (this.pointers.size >= 2) {
      // Two fingers: a pinch. A drawing in progress is dropped.
      this.cancel(true);
      this.pan = null;
      this.drag = null;
      this.startGesture();
      return;
    }
    const mouse = e.pointerType === 'mouse';
    if (mouse && e.button === 1 || mouse && e.button === 2) { this.startPan(e, p); return; }
    if (mouse && e.button !== 0) return;
    if (this.drawingTool) {
      const info = toolInfo(this.tool);
      if (info.how === 'drag' || info.how === 'free') { this.startStroke(e, p); return; }
      this.pan = { x: p[0], y: p[1], tx: this.tx, ty: this.ty, id: e.pointerId, moved: false }; // poly and click: a still click acts, a drag pans
      return;
    }
    this.pan = { x: p[0], y: p[1], tx: this.tx, ty: this.ty, id: e.pointerId, moved: false };
  }

  private startPan(e: PointerEvent, p: [number, number]): void {
    this.pan = { x: p[0], y: p[1], tx: this.tx, ty: this.ty, id: e.pointerId, moved: true };
    this.stage.classList.add('panning');
    e.preventDefault();
  }

  private startGesture(): void {
    const pts = [...this.pointers.values()];
    const [a, b] = [pts[0]!, pts[1]!];
    this.gesture = { d: Math.hypot(a[0] - b[0], a[1] - b[1]) || 1, cx: (a[0] + b[0]) / 2, cy: (a[1] + b[1]) / 2 };
  }

  private onMove(e: PointerEvent): void {
    if (!this.sheet) return;
    const p = this.rel(e);
    if (this.pointers.has(e.pointerId)) this.pointers.set(e.pointerId, p);
    if (this.pointers.size >= 2 && this.gesture) {
      const pts = [...this.pointers.values()];
      const [a, b] = [pts[0]!, pts[1]!];
      const d = Math.hypot(a[0] - b[0], a[1] - b[1]) || 1;
      const cx = (a[0] + b[0]) / 2;
      const cy = (a[1] + b[1]) / 2;
      this.tx += cx - this.gesture.cx;
      this.ty += cy - this.gesture.cy;
      this.zoomAt(cx, cy, d / this.gesture.d);
      this.gesture = { d, cx, cy };
      return;
    }
    if (this.poly) { this.last = p; this.invalidate(); }
    if (this.stroke && e.pointerId === this.stroke.id) {
      const how = toolInfo(this.stroke.tool).how;
      if (how === 'drag') this.stroke.pts[1] = p;
      else {
        const l = this.stroke.pts[this.stroke.pts.length - 1]!;
        if (Math.hypot(p[0] - l[0], p[1] - l[1]) >= 2) this.stroke.pts.push(p);
      }
      this.invalidate();
      return;
    }
    const pn = this.pan;
    if (pn && e.pointerId === pn.id) {
      const dx = p[0] - pn.x;
      const dy = p[1] - pn.y;
      if (!pn.moved && Math.hypot(dx, dy) > CLICK_SLOP) { pn.moved = true; this.stage.classList.add('panning'); }
      if (pn.moved) {
        this.tx = pn.tx + dx;
        this.ty = pn.ty + dy;
        this.moved();
      }
    }
  }

  private onUp(e: PointerEvent): void {
    const p = this.rel(e);
    this.pointers.delete(e.pointerId);
    this.stage.releasePointerCapture?.(e.pointerId);
    if (this.pointers.size < 2) this.gesture = null;
    if (this.stroke && e.pointerId === this.stroke.id) { this.endStroke(e.type === 'pointercancel'); return; }
    const pn = this.pan;
    if (pn && e.pointerId === pn.id) {
      this.pan = null;
      this.stage.classList.remove('panning');
      if (!pn.moved && e.type !== 'pointercancel') this.click(p);
    }
  }

  /** A still click: place text or a callout, add a corner, or pick a markup. */
  private click(p: [number, number]): void {
    const c = this.ctl.markup;
    if (this.drawingTool) {
      const info = toolInfo(this.tool);
      if (info.how === 'poly') this.polyClick(p);
      else if (info.how === 'click') this.addAnchored(this.tool, p);
      return;
    }
    // Pick: a markup under the click (any sketch of this sheet that is shown), else nothing.
    const id = this.hitTest(p[0], p[1]);
    if (id) {
      const f = c.markup(id);
      if (f && c.active?.id !== f.set.id) { c.activeId = f.set.id; }
      c.selectMarkup(id);
    } else if (c.selected) c.selectMarkup(null);
  }

  private startStroke(e: PointerEvent, p: [number, number]): void {
    this.cancel(true);
    this.stroke = { tool: this.tool, pts: [p], id: e.pointerId };
    e.preventDefault();
    this.invalidate();
  }

  private endStroke(cancelled: boolean): void {
    const st = this.stroke;
    this.stroke = null;
    this.invalidate();
    if (!st || cancelled) return;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const [x, y] of st.pts) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
    if (st.pts.length < 2 || Math.max(x1 - x0, y1 - y0) < 6) { this.ctl.markup.setStatus('Drag further to draw the markup (Esc cancels)'); return; }
    this.addShape(st.tool, st.pts);
  }

  private polyClick(p: [number, number]): void {
    const tool = this.tool;
    const now = Date.now();
    if (!this.poly) this.poly = { tool, pts: [], at: 0 };
    const poly = this.poly;
    const last = poly.pts[poly.pts.length - 1];
    if (last && Math.hypot(p[0] - last[0], p[1] - last[1]) < 6 && now - poly.at < 500) { this.finishPoly(); return; }
    if (tool === 'polygon' && poly.pts.length >= 3 && Math.hypot(p[0] - poly.pts[0]![0], p[1] - poly.pts[0]![1]) < 10) { this.finishPoly(); return; }
    poly.pts.push(p);
    poly.at = now;
    this.last = p;
    this.ctl.markup.setStatus(`${poly.pts.length} point${poly.pts.length === 1 ? '' : 's'}. Double click or press Enter to finish (Esc cancels)`);
    this.invalidate();
  }

  /** Finish a polyline or polygon with the corners so far. */
  finishPoly(): boolean {
    const poly = this.poly;
    this.poly = null;
    this.last = null;
    if (!poly) return false;
    const need = poly.tool === 'polygon' ? 3 : 2;
    if (poly.pts.length < need) { this.ctl.markup.setStatus(`A ${poly.tool} needs at least ${need} points`); this.invalidate(); return false; }
    this.addShape(poly.tool, poly.pts);
    return true;
  }

  /** Cancel a drawing in progress. */
  cancel(quiet = false): boolean {
    const had = this.stroke !== null || this.poly !== null;
    this.stroke = null;
    this.poly = null;
    this.last = null;
    if (had && !quiet) this.ctl.markup.setStatus('Drawing cancelled');
    this.invalidate();
    return had;
  }

  // ---------------------------------------------------------------- making markups

  /** A drawn shape (stage pixels) becomes a markup of the active sketch, in PDF user-space points. */
  addShape(tool: ToolId, screen: ReadonlyArray<readonly [number, number]>): Markup | null {
    const c = this.ctl.markup;
    const set = this.set;
    const info = toolInfo(tool);
    if (!set || !info.kind || !this.sheet) return null;
    let pts: ReadonlyArray<readonly [number, number]> = screen;
    if (info.how === 'drag') pts = [screen[0]!, screen[screen.length - 1]!];
    else if (info.how === 'free') {
      const flat = simplify(screen.flatMap((q) => [q[0], q[1]]), tool === 'cloudFree' ? 3 : 1.2);
      const p2: Array<[number, number]> = [];
      for (let i = 0; i < flat.length; i += 2) p2.push([flat[i]!, flat[i + 1]!]);
      pts = p2.length > 400 ? p2.filter((_q, i) => i % Math.ceil(p2.length / 400) === 0) : p2;
    }
    if (pts.length < 2) return null;
    const user = pts.map(([x, y]) => this.toUser(x, y)).map(([x, y]) => [Math.round(x * 100) / 100, Math.round(y * 100) / 100] as [number, number]);
    const m = newMarkup(info.kind, {
      author: c.author.trim() || 'unknown', colour: c.colour(tool), weight: c.weight, fill: c.fill, shape: { points: user, depth: 0 }, attach: { kind: 'none' },
    });
    const added = c.add(m, set);
    this.ctl.attachNew(set, added);
    return added;
  }

  /** A click places a text box or a callout (anchored at the click, the box beside it). */
  addAnchored(tool: ToolId, p: [number, number]): Markup | null {
    const c = this.ctl.markup;
    const set = this.set;
    const info = toolInfo(tool);
    const sh = this.sheet;
    if (!set || !info.kind || !sh || (info.kind !== 'text' && info.kind !== 'callout')) return null;
    const [ux, uy] = this.toUser(p[0], p[1]);
    const n = set.markups.filter((m) => m.anchor).length;
    const m = newMarkup(info.kind, {
      author: c.author.trim() || 'unknown', colour: c.colour(tool), weight: c.weight, text: c.text,
      anchor: { kind: 'point', point: [Math.round(ux * 100) / 100, Math.round(uy * 100) / 100, 0] }, offset: nextOffset(n, info.kind),
    });
    const added = c.add(m, set);
    this.ctl.attachNew(set, added);
    return added;
  }

  // ---------------------------------------------------------------- keys

  private onKey(e: KeyboardEvent): void {
    if (!this.visible) return;
    const c = this.ctl.markup;
    const editing = isEditable(e.target);
    const mod = e.ctrlKey || e.metaKey;
    if (e.key === 'Escape') {
      if (editing) return;
      if (this.cancel()) { e.stopImmediatePropagation(); e.preventDefault(); return; }
      if (c.tool !== 'select') { e.stopImmediatePropagation(); e.preventDefault(); c.setTool('select'); return; }
      if (c.selected) { e.stopImmediatePropagation(); e.preventDefault(); c.selectMarkup(null); return; }
      return;
    }
    if (editing) return;
    if (mod && !e.altKey && (e.key === 'z' || e.key === 'Z')) {
      e.stopImmediatePropagation(); e.preventDefault();
      if (e.shiftKey) c.redo(); else c.undo();
    } else if (mod && !e.altKey && (e.key === 'y' || e.key === 'Y')) {
      e.stopImmediatePropagation(); e.preventDefault();
      c.redo();
    } else if (e.key === 'Enter' && this.poly) {
      e.stopImmediatePropagation(); e.preventDefault();
      this.finishPoly();
    } else if ((e.key === 'Delete' || e.key === 'Backspace') && c.selected && !mod) {
      e.stopImmediatePropagation(); e.preventDefault();
      c.remove(c.selected);
    } else if ((e.key === '+' || e.key === '=') && !mod) {
      this.zoomAt(this.stage.clientWidth / 2, this.stage.clientHeight / 2, 1.25);
    } else if (e.key === '-' && !mod) {
      this.zoomAt(this.stage.clientWidth / 2, this.stage.clientHeight / 2, 0.8);
    } else if (e.key === '0' && !mod) this.fit();
  }

  // ---------------------------------------------------------------- hit test and moving

  /** The markup under a stage point (topmost first) among the sketches of this sheet. */
  hitTest(x: number, y: number): string | null {
    const sets = this.visibleSets();
    const px = x - this.tx;
    const py = y - this.ty;
    for (let si = sets.length - 1; si >= 0; si--) {
      const set = sets[si]!;
      for (let i = set.markups.length - 1; i >= 0; i--) {
        const m = set.markups[i]!;
        const h = this.hits.get(m.id);
        if (!h) continue;
        if (h.closed && h.filled && pointInPolygon(px, py, h.pts)) return m.id;
        if (distToPolyline(px, py, h.pts, h.closed) <= HIT_PX / 2) return m.id;
      }
    }
    return null;
  }

  private visibleSets(): MarkupSet[] {
    const sh = this.sheet;
    if (!sh) return [];
    return this.ctl.sketchesOn(sh.id).filter((s) => this.ctl.markup.inScope(s));
  }

  private startDrag(e: PointerEvent, m: Markup, set: MarkupSet): void {
    if (e.button !== 0 && e.pointerType === 'mouse') return;
    const sh = this.sheet!;
    e.stopPropagation();
    e.preventDefault();
    const c = this.ctl.markup;
    if (c.active?.id !== set.id) c.activeId = set.id;
    c.selectMarkup(m.id);
    if (set.readonly) return;
    const kind: 'shape' | 'box' = m.shape ? 'shape' : 'box';
    const from: Array<[number, number]> = m.shape ? m.shape.points.map((p) => [p[0], p[1]] as [number, number]) : [];
    const off: [number, number] = m.offset ? [m.offset[0], m.offset[1]] : [0, 0];
    this.drag = { id: m.id, sx: e.clientX, sy: e.clientY, kind, from, off, moved: false };
    const move = (ev: PointerEvent): void => {
      const d = this.drag;
      if (!d) return;
      const dx = ev.clientX - d.sx;
      const dy = ev.clientY - d.sy;
      if (!d.moved && Math.hypot(dx, dy) < 3) return;
      const f = c.markup(d.id);
      if (!f) return;
      if (!d.moved) { d.moved = true; c.record(f.set); }
      if (d.kind === 'shape') {
        // Move by the same displacement in user space: the page point under the pointer moves, whatever the rotation.
        const [ax, ay] = displayToUser(sh, 0, 0);
        const [bx, by] = displayToUser(sh, dx / this.scale, dy / this.scale);
        const ux = bx - ax;
        const uy = by - ay;
        f.m.shape = { points: d.from.map((p) => [Math.round((p[0] + ux) * 100) / 100, Math.round((p[1] + uy) * 100) / 100] as [number, number]), depth: 0 };
        f.m.modified = new Date().toISOString();
        c.emit(true);
      } else c.patch(d.id, { offset: [d.off[0] + dx / this.scale / sh.heightPt, d.off[1] + dy / this.scale / sh.heightPt] }, { quiet: true });
    };
    const up = (): void => {
      window.removeEventListener('pointermove', move, true);
      window.removeEventListener('pointerup', up, true);
      window.removeEventListener('pointercancel', up, true);
      const d = this.drag;
      this.drag = null;
      if (d?.moved) { const f = c.markup(d.id); if (d.kind === 'shape' && f) this.ctl.attachNew(f.set, f.m); c.emit(); }
    };
    window.addEventListener('pointermove', move, true);
    window.addEventListener('pointerup', up, true);
    window.addEventListener('pointercancel', up, true);
  }

  // ---------------------------------------------------------------- drawing the view

  invalidate(): void {
    if (this.frame) return;
    this.frame = requestAnimationFrame(() => {
      this.frame = 0;
      this.draw();
    });
  }

  /** Draw now (scripts and the smoke test). */
  drawNow(): void {
    if (this.frame) { cancelAnimationFrame(this.frame); this.frame = 0; }
    this.draw();
  }

  /** Keep the view clear of the edge chrome (the tool strip and drawer, the rails of a phone, the top and status bars). */
  private fitChrome(): void {
    fitToChrome(this.root);
  }

  private draw(): void {
    const sh = this.sheet;
    if (!sh || !this.visible) return;
    this.fitChrome();
    const c = this.ctl.markup;
    // The page picture: the whole-page canvas scaled to the zoom.
    const k = this.scale / this.baseScale;
    this.base.style.width = `${this.base.width}px`;
    this.base.style.height = `${this.base.height}px`;
    this.base.style.transform = `translate(${this.tx}px, ${this.ty}px) scale(${k})`;
    // Title, pager, sketch selector, draw button.
    const pages = this.ctl.sheetsOf(sh.docId);
    const idx = pages.findIndex((p) => p.id === sh.id);
    const doc = this.ctl.store.doc(sh.docId);
    this.title.textContent = doc ? `${doc.name}${pages.length > 1 ? '' : ''}` : sh.name;
    this.title.title = sh.name;
    this.pageLbl.textContent = `${idx + 1} / ${pages.length}`;
    this.prevBtn.disabled = idx <= 0;
    this.nextBtn.disabled = idx >= pages.length - 1;
    const sets = this.visibleSets();
    const key = sets.map((s) => `${s.id}:${s.title}:${s.readonly ? 1 : 0}`).join('|') + `|${c.activeId}`;
    if (this.sketchSel.dataset['key'] !== key) {
      this.sketchSel.dataset['key'] = key;
      this.sketchSel.textContent = '';
      this.sketchSel.appendChild(el('option', '', { value: '' }, sets.length ? 'No sketch' : 'No sketch yet'));
      for (const s of sets) this.sketchSel.appendChild(el('option', '', { value: s.id }, `${s.title}${s.readonly ? ' (read-only)' : ''}`));
      this.sketchSel.appendChild(el('option', '', { value: '__new' }, 'New sketch...'));
    }
    const act = this.set;
    if (this.sketchSel.value !== (act?.id ?? '')) this.sketchSel.value = act?.id ?? '';
    this.drawBtn.setAttribute('aria-pressed', String(c.editing));
    this.drawBtn.textContent = c.editing ? 'Done' : 'Draw';
    this.stage.classList.toggle('drawing', this.drawingTool);
    this.drawPlacement(sh);
    // Sketches.
    this.layer.textContent = '';
    this.hits.clear();
    this.layer.setAttribute('transform', `translate(${this.tx} ${this.ty})`);
    const interactive = !this.drawingTool;
    for (const set of sets) {
      const faded = !!act && set.id !== act.id && c.editing;
      for (const m of set.markups) {
        const L = layoutSheetMarkup(m, sh, { scale: this.scale, selected: m.id === c.selected, faded });
        if (!L.ops.length) continue;
        const g = svgEl('g', { 'data-mk': m.id, 'data-number': String(m.number), 'data-set': set.id });
        renderOps(g, L.ops);
        this.hits.set(m.id, L.hit);
        if (L.hit && (interactive || set.readonly)) {
          const { pts, closed, filled } = L.hit;
          const hit = svgEl(closed ? 'polygon' : 'polyline', { points: pts.map((v) => v.toFixed(1)).join(' '), fill: filled ? 'rgba(0,0,0,0)' : 'none', stroke: 'rgba(0,0,0,0)', 'stroke-width': HIT_PX, 'stroke-linejoin': 'round' });
          hit.setAttribute('data-hit', m.id);
          hit.style.pointerEvents = filled ? 'all' : 'stroke';
          hit.style.cursor = set.readonly ? 'pointer' : c.editing ? 'move' : 'pointer';
          hit.addEventListener('pointerdown', (e: PointerEvent) => {
            if (this.pointers.size) return;
            if (c.editing && !set.readonly) this.startDrag(e, m, set);
            else if (e.button === 0 || e.pointerType !== 'mouse') { e.stopPropagation(); if (c.active?.id !== set.id) c.activeId = set.id; c.selectMarkup(m.id); }
          });
          g.appendChild(hit);
        }
        this.layer.appendChild(g);
      }
    }
    // The drawing in progress.
    const st = this.stroke;
    const pl = this.poly;
    let tmp: Markup | null = null;
    const toFrac = (pts: Array<[number, number]>): Array<[number, number]> => pts.map(([x, y]) => this.toUser(x, y));
    const preview = (tool: ToolId, pts: Array<[number, number]>): Markup | null => {
      const info = toolInfo(tool);
      if (!info.kind || pts.length < 2) return null;
      const p = info.how === 'drag' ? [pts[0]!, pts[pts.length - 1]!] : pts;
      return newMarkup(info.kind, { id: 'preview', number: act?.nextNumber ?? 1, author: '', colour: c.colour(tool), weight: c.weight, fill: c.fill, shape: { points: toFrac(p), depth: 0 }, attach: { kind: 'none' } });
    };
    if (st && st.pts.length > 1) tmp = preview(st.tool, st.pts);
    else if (pl) {
      const pts = [...pl.pts];
      if (this.last) pts.push(this.last);
      tmp = preview(pl.tool, pts);
      for (const [x, y] of pl.pts) this.layer.appendChild(svgEl('circle', { cx: x - this.tx, cy: y - this.ty, r: 3.5, fill: '#ffffff', stroke: '#3b9cff', 'stroke-width': 1.5 }));
    }
    if (tmp) {
      const g = svgEl('g', { 'data-mk-preview': tmp.kind });
      renderOps(g, layoutSheetMarkup(tmp, sh, { scale: this.scale, noBadge: true }).ops);
      this.layer.appendChild(g);
    }
    this.updateInfo();
    // The drawing toolbar.
    const show = c.editing && !!act && !act.readonly;
    const ov = { width: this.stage.clientWidth, height: this.stage.clientHeight, insets: { top: 0, right: 0, bottom: 0, left: 0 }, reserved: [] } as never;
    this.bar?.update(show, ov, this.poly?.pts.length ?? 0, () => this.finishPoly());
  }

  /** The placement row, the overlay toggle and the model overlay itself (vector outlines of the plan cut through the placement). */
  private drawPlacement(sh: Sheet): void {
    const c = this.ctl;
    const p = sh.placement;
    const placeable = c.place.loaded;
    this.pstat.textContent = placementStatus(p) + (p ? ` · ${p.level.name ?? `level ${p.level.elevation} m`}` : '');
    const geoNote = !p ? c.place.geoNotes.get(sh.id) : undefined;
    this.pstat.title = geoNote ?? (p ? `${p.source}. Level at ${p.level.elevation} m.` : 'This sheet is a plain drawing: sketches on it stay on the sheet');
    this.placeBtn.textContent = p ? 'Place again…' : 'Place in model…';
    this.placeBtn.disabled = !placeable;
    const plan = !!p && isPlan(p);
    const on = plan && c.overlayOn.has(sh.id);
    this.ovlBtn.hidden = !plan;
    this.opac.hidden = !plan || !on;
    this.ovlBtn.setAttribute('aria-pressed', String(on));
    if (document.activeElement !== this.opac) this.opac.value = String(Math.round(c.overlayOpacity * 100));
    this.misfit.hidden = !(plan && p!.residual !== undefined);
    if (p?.residual !== undefined) this.misfit.textContent = `Misfit ±${mm(p.residual)} mm`;
    // The overlay canvas covers the stage at the screen's pixel density.
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const W = this.stage.clientWidth;
    const H = this.stage.clientHeight;
    if (this.ovl.width !== Math.round(W * dpr) || this.ovl.height !== Math.round(H * dpr)) {
      this.ovl.width = Math.round(W * dpr);
      this.ovl.height = Math.round(H * dpr);
      this.ovl.style.width = `${W}px`;
      this.ovl.style.height = `${H}px`;
    }
    const g = this.ovl.getContext('2d')!;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H);
    this.overlayDrawn = 0;
    if (!on || !p) return;
    const cut = c.place.cut(p.level.elevation);
    const m = modelToPixels(p, (ux, uy) => this.toStage(ux, uy));
    this.overlayDrawn = drawCut(g, cut, m, { color: '#d6336c', alpha: c.overlayOpacity, width: Math.max(1, Math.min(2, this.scale * 0.8)), view: [0, 0, W, H] });
  }

  /** Author and contents of the selected markup (the annotations of a PDF show them here). */
  private updateInfo(): void {
    const c = this.ctl.markup;
    const f = c.selected ? c.markup(c.selected) : null;
    const sh = this.sheet;
    if (!f || !sh || f.set.frame?.kind !== 'sheet' || f.set.frame.sheet !== sh.id || (!f.set.readonly && !f.m.text && !isAnchorKind(f.m.kind))) {
      this.info.style.display = 'none';
      return;
    }
    this.info.style.display = 'block';
    this.info.textContent = '';
    const who = f.m.author && f.m.author !== 'unknown' ? f.m.author : '';
    const head = el('div', '', undefined, '');
    head.append(el('b', '', undefined, `${f.set.readonly ? 'Imported' : 'Sketch'} · ${f.set.title}`));
    this.info.appendChild(head);
    if (who) this.info.appendChild(el('div', '', { 'data-sv-info': 'author' }, `Author: ${who}`));
    if (f.m.text) this.info.appendChild(el('div', '', { 'data-sv-info': 'text' }, f.m.text));
  }

  // ---------------------------------------------------------------- state for scripts and tests

  state(): { open: boolean; sheet: string | null; scale: number; tx: number; ty: number; baseScale: number; detailScale: number; renders: { base: number; detail: number }; detailShown: boolean; overlayDrawn: number } {
    return {
      open: this.visible, sheet: this.sheet?.id ?? null, scale: this.scale, tx: this.tx, ty: this.ty, baseScale: this.baseScale,
      detailScale: this.detailScale, renders: { ...this.renders }, detailShown: this.detail.style.display === 'block', overlayDrawn: this.overlayDrawn,
    };
  }
}

