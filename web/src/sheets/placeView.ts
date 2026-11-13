// The placement view: "Place in model...". The sheet on one side, the plan of the chosen storey on the other (the plan cut, as vectors),
// and the user picks point A on the sheet then A in the model, B and B, optionally more. The model picks snap to corners and edges of
// the cut. The transform is fitted as the points come in (two pairs exact, three or more least squares, or "Use drawing scale" with
// one pair, the scale and a rotation) and shown at once as the model overlay on the sheet, with Accept, Redo and Cancel. On a phone the
// two sides are shown one after the other, in steps. DOM only; the maths is placement.ts, the cut sectionCut.ts, the service
// placeService.ts. Docs: docs-features/sheets.md ("Placing a sheet").

import { svgEl } from '../ui/overlay';
import { el } from '../ui/dom';
import { STATUS_H } from '../ui/statusBar';
import { STRIP_W } from '../ui/toolbarView';
import { TOPBAR_H } from '../ui/topBar';
import type { SheetsController } from './controller';
import type { Level } from './placeService';
import { displayToUser, userToDisplay } from './model';
import type { Sheet } from './model';
import { fitToChrome } from './chrome';
import { drawCut, modelToPixels } from './overlayDraw';
import { fitSimilarity, fromScale, mm } from './placement';
import type { PointPair, SheetPlacement, Similarity, Vec2 } from './placement';
import { snapToCut } from './sectionCut';
import type { PlanCut } from './sectionCut';

const STYLE_ID = 'sheet-place-styles';
const CSS = `
#sheet-place{position:absolute;left:${STRIP_W}px;right:0;top:${TOPBAR_H}px;bottom:${STATUS_H}px;z-index:14;display:none;flex-direction:column;background:#1b2029;color:#dfe6ee;font:12px/1.35 system-ui,sans-serif}
#sheet-place.on{display:flex}
#sheet-place *{box-sizing:border-box}
#sheet-place .pv-bar{flex:0 0 auto;display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:5px 8px;background:#141820;border-bottom:1px solid #262d3a}
#sheet-place button,#sheet-place select,#sheet-place input{background:#1c2f45;color:#eaf2ff;border:1px solid #3b6c9c;border-radius:8px;font:inherit;min-height:32px;padding:0 10px}
#sheet-place button{cursor:pointer}
#sheet-place button:disabled{opacity:.4;cursor:default}
#sheet-place button[aria-pressed=true]{background:#1f4a7a;border-color:#3b9cff}
#sheet-place .pv-accept{background:#1f6fe5;border-color:#3b9cff;font-weight:700}
#sheet-place .pv-title{flex:1 1 140px;min-width:0;font-weight:700;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#sheet-place .pv-seg{display:flex}
#sheet-place .pv-seg button{border-radius:0}
#sheet-place .pv-seg button:first-child{border-radius:8px 0 0 8px}
#sheet-place .pv-seg button:last-child{border-radius:0 8px 8px 0}
#sheet-place .pv-info{flex:0 0 auto;padding:5px 8px;background:#10141b;border-bottom:1px solid #262d3a;display:flex;flex-wrap:wrap;gap:4px 12px;align-items:center}
#sheet-place .pv-hint{font-weight:600;color:#ffd27a;flex:1 1 220px}
#sheet-place .pv-res{color:#9fc4ee}
#sheet-place .pv-scale{display:none;gap:6px;align-items:center;flex-wrap:wrap}
#sheet-place .pv-scale.on{display:flex}
#sheet-place .pv-scale input{width:76px}
#sheet-place .pv-confirm{display:none;gap:6px;align-items:center;flex-wrap:wrap;color:#ffb4a8}
#sheet-place .pv-confirm.on{display:flex}
#sheet-place .pv-panes{flex:1 1 auto;min-height:0;display:flex}
#sheet-place .pv-pane{flex:1 1 50%;min-width:0;display:flex;flex-direction:column;border-right:1px solid #262d3a}
#sheet-place .pv-pane:last-child{border-right:0}
#sheet-place .pv-ph{flex:0 0 auto;padding:3px 8px;background:#141820;color:#9fc4ee;font-weight:700}
#sheet-place .pv-stage{position:relative;flex:1 1 auto;min-height:0;overflow:hidden;touch-action:none;cursor:crosshair;background:#3a404a}
#sheet-place .pv-model .pv-stage{background:#1b2029}
#sheet-place canvas{position:absolute;left:0;top:0;transform-origin:0 0}
#sheet-place canvas.pv-page{background:#fff;box-shadow:0 2px 14px rgba(0,0,0,.5)}
#sheet-place svg{position:absolute;left:0;top:0;width:100%;height:100%;overflow:visible;pointer-events:none}
#sheet-place .pv-steps{display:none;flex:0 0 auto;gap:6px;padding:4px 8px;background:#141820;border-bottom:1px solid #262d3a}
#sheet-place .pv-msg{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);padding:8px 12px;border-radius:8px;background:rgba(20,24,32,.92);max-width:80%;text-align:center}
@media (max-width:700px){
#sheet-place .pv-steps{display:flex}
#sheet-place .pv-panes .pv-pane{display:none;flex:1 1 100%}
#sheet-place[data-focus=sheet] .pv-sheet{display:flex}
#sheet-place[data-focus=model] .pv-model{display:flex}
#sheet-place .pv-bar button,#sheet-place .pv-bar select{padding:0 8px}
}
`;

const LETTERS = 'ABCDEFGH';
const PICK_R = 7;

interface Pair { sheet?: Vec2; model?: Vec2 }

/** Pan and zoom of one pane: wheel, drag, pinch; a still click is reported. */
class Pane {
  scale = 1;
  tx = 0;
  ty = 0;
  readonly stage: HTMLDivElement;
  onClick: (x: number, y: number) => void = () => undefined;
  onHover: (x: number, y: number) => void = () => undefined;
  onView: () => void = () => undefined;
  private readonly pts = new Map<number, [number, number]>();
  private pan: { x: number; y: number; tx: number; ty: number; moved: boolean } | null = null;
  private pinch: { d: number } | null = null;

  constructor(stage: HTMLDivElement) {
    this.stage = stage;
    stage.addEventListener('pointerdown', (e) => {
      stage.setPointerCapture?.(e.pointerId);
      const p = this.rel(e);
      this.pts.set(e.pointerId, p);
      if (this.pts.size >= 2) { this.pan = null; const [a, b] = [...this.pts.values()]; this.pinch = { d: Math.hypot(a![0] - b![0], a![1] - b![1]) || 1 }; return; }
      const mouse = e.pointerType === 'mouse';
      if (mouse && e.button !== 0) { this.pan = { x: p[0], y: p[1], tx: this.tx, ty: this.ty, moved: true }; e.preventDefault(); return; }
      this.pan = { x: p[0], y: p[1], tx: this.tx, ty: this.ty, moved: false };
    });
    stage.addEventListener('pointermove', (e) => {
      const p = this.rel(e);
      if (this.pts.has(e.pointerId)) this.pts.set(e.pointerId, p);
      if (this.pts.size >= 2 && this.pinch) {
        const [a, b] = [...this.pts.values()];
        const d = Math.hypot(a![0] - b![0], a![1] - b![1]) || 1;
        this.zoomAt((a![0] + b![0]) / 2, (a![1] + b![1]) / 2, d / this.pinch.d);
        this.pinch = { d };
        return;
      }
      if (this.pan) {
        const dx = p[0] - this.pan.x, dy = p[1] - this.pan.y;
        if (!this.pan.moved && Math.hypot(dx, dy) > 5) this.pan.moved = true;
        if (this.pan.moved) { this.tx = this.pan.tx + dx; this.ty = this.pan.ty + dy; this.onView(); }
      } else this.onHover(p[0], p[1]);
    });
    const up = (e: PointerEvent): void => {
      const p = this.rel(e);
      this.pts.delete(e.pointerId);
      if (this.pts.size < 2) this.pinch = null;
      stage.releasePointerCapture?.(e.pointerId);
      const pn = this.pan;
      this.pan = null;
      if (pn && !pn.moved && e.type !== 'pointercancel') this.onClick(p[0], p[1]);
    };
    stage.addEventListener('pointerup', up);
    stage.addEventListener('pointercancel', up);
    stage.addEventListener('wheel', (e) => {
      e.preventDefault();
      const r = stage.getBoundingClientRect();
      this.zoomAt(e.clientX - r.left, e.clientY - r.top, Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.0018)));
    }, { passive: false });
    stage.addEventListener('contextmenu', (e) => e.preventDefault());
  }

  private rel(e: PointerEvent | MouseEvent): [number, number] {
    const r = this.stage.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  }

  zoomAt(x: number, y: number, k: number): void {
    const s = Math.max(1e-4, Math.min(1e5, this.scale * k));
    const f = s / this.scale;
    this.tx = x - (x - this.tx) * f;
    this.ty = y - (y - this.ty) * f;
    this.scale = s;
    this.onView();
  }

  /** Fit a rectangle (x0, y0, x1, y1 in the pane's own unit) with a margin; `flipY` for plan metres (y up). */
  fit(box: [number, number, number, number], flipY = false): void {
    const W = Math.max(40, this.stage.clientWidth);
    const H = Math.max(40, this.stage.clientHeight);
    const w = Math.max(1e-6, box[2] - box[0]);
    const h = Math.max(1e-6, box[3] - box[1]);
    const m = 16;
    this.scale = Math.max(1e-4, Math.min((W - 2 * m) / w, (H - 2 * m) / h));
    this.tx = (W - w * this.scale) / 2 - box[0] * this.scale;
    this.ty = flipY ? (H - h * this.scale) / 2 + box[3] * this.scale : (H - h * this.scale) / 2 - box[1] * this.scale;
    this.onView();
  }
}

export class PlaceView {
  readonly root: HTMLDivElement;
  private sheet: Sheet | null = null;
  private pairs: Pair[] = [];
  private mode: 'points' | 'scale' = 'points';
  private level: Level | null = null;
  private cut: PlanCut | null = null;
  private focus: 'sheet' | 'model' = 'sheet';
  private readonly sp: Pane;
  private readonly mp: Pane;
  private readonly page: HTMLCanvasElement;
  private readonly ovl: HTMLCanvasElement;
  private readonly plan: HTMLCanvasElement;
  private readonly sMarks: SVGGElement;
  private readonly mMarks: SVGGElement;
  private readonly title: HTMLDivElement;
  private readonly levelSel: HTMLSelectElement;
  private readonly hint: HTMLDivElement;
  private readonly res: HTMLDivElement;
  private readonly scaleRow: HTMLDivElement;
  private readonly scaleIn: HTMLInputElement;
  private readonly rotIn: HTMLInputElement;
  private readonly confirm: HTMLDivElement;
  private readonly confirmText: HTMLSpanElement;
  private readonly btn: Record<string, HTMLButtonElement> = {};
  private readonly msgS: HTMLDivElement;
  private readonly msgM: HTMLDivElement;
  private pageScale = 1;
  private frame = 0;
  private gen = 0;
  private hover: { snap: [number, number]; kind: string } | null = null;
  private pending: SheetPlacement | null = null;
  /** Each pane is fitted to its content once it has a size (on a phone the hidden one has none until its step). */
  private needFit = { sheet: false, model: false };
  private fitBox: [number, number, number, number] | null = null;

  constructor(private readonly ctl: SheetsController, host: HTMLElement) {
    if (!document.getElementById(STYLE_ID)) {
      const st = document.createElement('style');
      st.id = STYLE_ID;
      st.textContent = CSS;
      document.head.appendChild(st);
    }
    const root = el('div', '', { id: 'sheet-place', role: 'dialog', 'aria-label': 'Place the sheet in the model', 'data-help-key': 'Place in model' });
    const mk = (label: string, act: string, title: string, cls = ''): HTMLButtonElement => {
      const b = el('button', cls, { type: 'button', 'data-act': act, title }, label) as HTMLButtonElement;
      this.btn[act] = b;
      return b;
    };
    const bar = el('div', 'pv-bar');
    this.title = el('div', 'pv-title', { 'data-pv': 'title' });
    this.levelSel = el('select', '', { 'data-pv': 'level', 'aria-label': 'Storey', title: 'The storey this sheet shows: the model side is the plan cut about 1.2 m above it' }) as HTMLSelectElement;
    const seg = el('div', 'pv-seg');
    const mPoints = mk('Two points', 'mode-points', 'Pick two points on the sheet and the same two in the model (a third makes a least-squares fit)');
    const mScale = mk('Use drawing scale', 'mode-scale', 'Enter the scale of the drawing (1:100), pick one point on the sheet and in the model, and give the rotation');
    seg.append(mPoints, mScale);
    const add = mk('Add point', 'add', 'Another pair of points: three or more are fitted by least squares and the misfit is shown');
    const undo = mk('Undo point', 'undo', 'Remove the last point you picked');
    const redo = mk('Redo', 'redo', 'Start the points again');
    const accept = mk('Accept', 'accept', 'Place the sheet like this', 'pv-accept');
    const cancel = mk('Cancel', 'cancel', 'Close without placing');
    bar.append(cancel, this.title, this.levelSel, seg, add, undo, redo, accept);
    const info = el('div', 'pv-info');
    this.hint = el('div', 'pv-hint', { role: 'status', 'data-pv': 'hint' });
    this.res = el('div', 'pv-res', { 'data-pv': 'result' });
    this.scaleRow = el('div', 'pv-scale', { 'data-pv': 'scale-row' });
    this.scaleIn = el('input', '', { type: 'number', min: '1', step: '1', value: '100', 'data-pv': 'scale', 'aria-label': 'Drawing scale denominator', title: 'The drawing is 1:N: N is the number to enter' }) as HTMLInputElement;
    this.rotIn = el('input', '', { type: 'number', step: '1', value: '0', 'data-pv': 'rotation', 'aria-label': 'Rotation in degrees', title: 'Degrees, counter-clockwise, that the sheet is turned against the model (0: the drawing and the model have the same north)' }) as HTMLInputElement;
    this.scaleRow.append(el('span', '', undefined, 'Scale 1:'), this.scaleIn, el('span', '', undefined, 'Rotation °'), this.rotIn);
    this.confirm = el('div', 'pv-confirm', { role: 'alertdialog', 'data-pv': 'confirm' });
    this.confirmText = el('span');
    const yes = mk('Place anyway', 'confirm-yes', 'Attach the shapes again; those that were on elements may no longer be');
    const no = mk('Keep editing', 'confirm-no', 'Go back to the points');
    this.confirm.append(this.confirmText, yes, no);
    info.append(this.hint, this.res, this.scaleRow, this.confirm);
    const steps = el('div', 'pv-steps', { 'data-pv': 'steps' });
    const stSheet = mk('Sheet', 'focus-sheet', 'Show the sheet');
    const stModel = mk('Model', 'focus-model', 'Show the model plan');
    steps.append(stSheet, stModel);
    const panes = el('div', 'pv-panes');
    // The sheet side.
    const sPane = el('div', 'pv-pane pv-sheet');
    sPane.appendChild(el('div', 'pv-ph', undefined, 'Sheet'));
    const sStage = el('div', 'pv-stage', { 'data-pv': 'sheet-stage' });
    this.page = el('canvas', 'pv-page', { 'data-pv': 'page' }) as HTMLCanvasElement;
    this.ovl = el('canvas', '', { 'data-pv': 'preview' }) as HTMLCanvasElement;
    const sSvg = svgEl('svg', {}) as SVGSVGElement;
    this.sMarks = svgEl('g', {}) as SVGGElement;
    sSvg.appendChild(this.sMarks);
    this.msgS = el('div', 'pv-msg', { role: 'status' });
    this.msgS.style.display = 'none';
    sStage.append(this.page, this.ovl, sSvg, this.msgS);
    sPane.appendChild(sStage);
    // The model side.
    const mPane = el('div', 'pv-pane pv-model');
    mPane.appendChild(el('div', 'pv-ph', { 'data-pv': 'model-head' }, 'Model'));
    const mStage = el('div', 'pv-stage', { 'data-pv': 'model-stage' });
    this.plan = el('canvas', '', { 'data-pv': 'plan' }) as HTMLCanvasElement;
    const mSvg = svgEl('svg', {}) as SVGSVGElement;
    this.mMarks = svgEl('g', {}) as SVGGElement;
    mSvg.appendChild(this.mMarks);
    this.msgM = el('div', 'pv-msg', { role: 'status' });
    this.msgM.style.display = 'none';
    mStage.append(this.plan, mSvg, this.msgM);
    mPane.appendChild(mStage);
    panes.append(sPane, mPane);
    root.append(bar, steps, info, panes);
    host.appendChild(root);
    this.root = root;
    this.sp = new Pane(sStage);
    this.mp = new Pane(mStage);
    this.sp.onView = () => this.invalidate();
    this.mp.onView = () => this.invalidate();
    this.sp.onClick = (x, y) => this.pickSheet(x, y);
    this.mp.onClick = (x, y) => this.pickModel(x, y);
    this.mp.onHover = (x, y) => this.hoverModel(x, y);

    cancel.addEventListener('click', () => ctl.closePlace());
    redo.addEventListener('click', () => this.reset());
    undo.addEventListener('click', () => this.undo());
    add.addEventListener('click', () => { this.pairs.push({}); this.update(); });
    accept.addEventListener('click', () => this.accept(false));
    yes.addEventListener('click', () => this.accept(true));
    no.addEventListener('click', () => { this.pending = null; this.update(); });
    mPoints.addEventListener('click', () => { this.mode = 'points'; this.update(); });
    mScale.addEventListener('click', () => { this.mode = 'scale'; this.update(); });
    stSheet.addEventListener('click', () => { this.focus = 'sheet'; this.update(); });
    stModel.addEventListener('click', () => { this.focus = 'model'; this.update(); });
    this.scaleIn.addEventListener('input', () => this.update());
    this.rotIn.addEventListener('input', () => this.update());
    this.levelSel.addEventListener('change', () => {
      const lv = this.ctl.place.levels()[Number(this.levelSel.value)];
      if (lv) { this.level = lv; this.loadCut(true); this.update(); }
    });
    window.addEventListener('keydown', (e) => {
      if (!this.root.classList.contains('on')) return;
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'SELECT')) return;
      if (e.key === 'Escape') { e.stopImmediatePropagation(); e.preventDefault(); ctl.closePlace(); }
    }, true);
    new ResizeObserver(() => { if (this.sheet) this.invalidate(); }).observe(root);
  }

  get visible(): boolean {
    return this.root.classList.contains('on');
  }

  // ---------------------------------------------------------------- show

  async show(sheetId: string | null): Promise<void> {
    if (sheetId === null) {
      this.root.classList.remove('on');
      document.body.classList.remove('sheet-place-open');
      this.sheet = null;
      this.gen++;
      return;
    }
    const sh = this.ctl.store.sheet(sheetId);
    if (!sh) return;
    this.sheet = sh;
    this.fitBox = null;
    this.root.dataset['focus'] = 'sheet';
    this.pairs = (sh.placement?.pairs ?? []).map((p) => ({ sheet: [...p.sheet] as Vec2, model: [...p.model] as Vec2 }));
    if (!this.pairs.length) this.pairs = [{}];
    this.mode = sh.placement?.drawingScale ? 'scale' : 'points';
    if (sh.placement?.drawingScale) {
      this.scaleIn.value = String(Math.round(sh.placement.drawingScale));
      this.rotIn.value = String(Math.round(((sh.placement.transform.rotation * 180) / Math.PI) * 100) / 100);
    }
    this.pending = null;
    this.focus = 'sheet';
    const levels = this.ctl.place.levels();
    this.level = (sh.placement ? this.ctl.place.levelOf(sh.placement) : undefined) ?? this.ctl.place.guessLevel(sh) ?? levels[0] ?? null;
    this.levelSel.textContent = '';
    levels.forEach((l, i) => this.levelSel.appendChild(el('option', '', { value: String(i) }, `${l.name} (${Math.round(l.elevation * 100) / 100} m)`)));
    const li = levels.findIndex((l) => this.level && l.index === this.level.index && Math.abs(l.elevation - this.level.elevation) < 0.01);
    this.levelSel.value = String(Math.max(0, li));
    this.root.classList.add('on');
    document.body.classList.add('sheet-place-open');
    this.title.textContent = `Place ${sh.name} in the model`;
    this.loadCut(false);
    const gen = ++this.gen;
    this.msgS.textContent = 'Loading the sheet...';
    this.msgS.style.display = '';
    this.pageScale = Math.min(4, 3600 / Math.max(sh.widthPt, sh.heightPt));
    try {
      const r = await this.ctl.render(sh, this.page, this.pageScale);
      await r.done;
      if (gen !== this.gen) return;
      this.msgS.style.display = 'none';
    } catch (e) {
      if (gen !== this.gen) return;
      this.msgS.textContent = `The sheet could not be drawn: ${e instanceof Error ? e.message : String(e)}`;
    }
    this.needFit.sheet = true;
    this.update();
  }

  private loadCut(refit: boolean): void {
    if (!this.level) { this.cut = null; return; }
    this.cut = this.ctl.place.cut(this.level.elevation);
    this.msgM.style.display = this.cut.elements.length ? 'none' : '';
    this.msgM.textContent = 'Nothing is cut at this level. Choose another storey.';
    const b = this.ctl.place.cutBounds(this.level.elevation);
    if (b && (refit || !this.fitBox)) { this.fitBox = b; this.needFit.model = true; }
    this.root.querySelector('[data-pv=model-head]')!.textContent = `Model, ${this.level.name}, plan cut at ${Math.round((this.level.elevation + 1.2) * 100) / 100} m`;
  }

  // ---------------------------------------------------------------- coordinates

  /** Stage pixels of the sheet pane to PDF user space, and back. */
  private sheetToUser(x: number, y: number): Vec2 {
    return displayToUser(this.sheet!, (x - this.sp.tx) / this.sp.scale, (y - this.sp.ty) / this.sp.scale);
  }
  private userToSheetPx(ux: number, uy: number): Vec2 {
    const [dx, dy] = userToDisplay(this.sheet!, ux, uy);
    return [this.sp.tx + dx * this.sp.scale, this.sp.ty + dy * this.sp.scale];
  }
  private modelPx(X: number, Y: number): Vec2 {
    return [this.mp.tx + X * this.mp.scale, this.mp.ty - Y * this.mp.scale];
  }
  private pxToModel(x: number, y: number): Vec2 {
    return [(x - this.mp.tx) / this.mp.scale, -(y - this.mp.ty) / this.mp.scale];
  }

  // ---------------------------------------------------------------- picking

  private current(): Pair {
    if (!this.pairs.length) this.pairs.push({});
    return this.pairs[this.pairs.length - 1]!;
  }
  private complete(p: Pair): p is Required<Pair> {
    return !!p.sheet && !!p.model;
  }

  private pickSheet(x: number, y: number): void {
    if (!this.sheet) return;
    this.pending = null;
    let cur = this.current();
    if (this.complete(cur)) {
      if (this.mode === 'scale') this.pairs = [{}]; // one pair is all the scale needs: a new pick starts it again
      else this.pairs.push({});
      cur = this.current();
    }
    cur.sheet = this.sheetToUser(x, y);
    this.focus = 'model';
    this.update();
  }

  private pickModel(x: number, y: number): void {
    this.pending = null;
    const cur = this.current();
    if (!cur.sheet) { this.setHint('Pick the point on the sheet first'); return; }
    const m = this.pxToModel(x, y);
    const snap = this.cut ? snapToCut(this.cut, m[0], m[1], 12 / this.mp.scale) : null;
    cur.model = snap ? snap.point : m;
    this.focus = 'sheet';
    this.update();
  }

  private hoverModel(x: number, y: number): void {
    if (!this.cut) return;
    const m = this.pxToModel(x, y);
    const s = snapToCut(this.cut, m[0], m[1], 12 / this.mp.scale);
    const next = s ? { snap: s.point, kind: s.kind } : null;
    if (JSON.stringify(next) !== JSON.stringify(this.hover)) { this.hover = next; this.invalidate(); }
  }

  private undo(): void {
    this.pending = null;
    const cur = this.current();
    if (cur.model) delete cur.model;
    else if (cur.sheet) delete cur.sheet;
    else if (this.pairs.length > 1) { this.pairs.pop(); const c = this.current(); if (c.model) delete c.model; }
    this.update();
  }

  private reset(): void {
    this.pending = null;
    this.pairs = [{}];
    this.focus = 'sheet';
    this.update();
  }

  // ---------------------------------------------------------------- the fit

  private completePairs(): PointPair[] {
    return this.pairs.filter((p): p is Required<Pair> => this.complete(p)).map((p) => ({ sheet: p.sheet, model: p.model }));
  }

  /** The placement the points give now, or why not. */
  result(): { transform: Similarity; residual?: number; source: string; drawingScale?: number } | { error: string } {
    const cp = this.completePairs();
    if (this.mode === 'scale') {
      if (!cp.length) return { error: 'Pick one point on the sheet and the same point in the model' };
      const n = Number(this.scaleIn.value);
      const r = fromScale(n, Number(this.rotIn.value || 0), cp[0]!);
      return r.ok ? { transform: r.transform, source: `scale 1:${Math.round(n)}`, drawingScale: n } : { error: r.error };
    }
    if (cp.length < 2) return { error: cp.length === 1 ? 'Pick the second point: on the sheet, then in the model' : 'Pick the first point: on the sheet, then in the model' };
    const f = fitSimilarity(cp);
    return f.ok ? { transform: f.transform, ...(f.residual !== undefined ? { residual: f.residual } : {}), source: `${cp.length} points` } : { error: f.error };
  }

  private setHint(t: string): void {
    this.hint.textContent = t;
  }

  private update(): void {
    const sh = this.sheet;
    if (!sh) return;
    const cp = this.completePairs();
    const cur = this.current();
    const idx = this.pairs.length - 1;
    const letter = LETTERS[Math.min(idx, LETTERS.length - 1)]!;
    const r = this.result();
    const ready = !('error' in r);
    if (this.confirm.classList.contains('on') && !this.pending) this.confirm.classList.remove('on');
    if (this.pending) this.confirm.classList.add('on');
    // What to do next.
    let hint: string;
    if (ready && this.complete(cur)) hint = this.mode === 'scale' ? 'Check the overlay on the sheet. Accept, or change the scale and rotation.' : `Check the overlay on the sheet. Accept, add a point for a better fit, or Redo.`;
    else if (!cur.sheet) hint = `Click point ${letter} on the sheet`;
    else hint = `Now click the same point ${letter} in the model (it snaps to corners and edges)`;
    if (this.pending) hint = 'Some shapes would leave the elements they are attached to.';
    this.setHint(hint);
    if ('error' in r) this.res.textContent = '';
    else {
      const t = r.transform;
      const rot = ((t.rotation * 180) / Math.PI + 540) % 360 - 180;
      this.res.textContent = `Scale 1:${Math.round(t.scale / ((25.4 / 72 / 1000)))}, rotation ${Math.round(rot * 100) / 100}°${r.residual !== undefined ? `, misfit ±${mm(r.residual)} mm` : cp.length >= 2 ? ', 2 points (exact)' : ''}`;
    }
    this.scaleRow.classList.toggle('on', this.mode === 'scale');
    this.btn['mode-points']!.setAttribute('aria-pressed', String(this.mode === 'points'));
    this.btn['mode-scale']!.setAttribute('aria-pressed', String(this.mode === 'scale'));
    this.btn['accept']!.disabled = !ready;
    this.btn['add']!.disabled = this.mode === 'scale' || !(this.complete(cur) && ready) || this.pairs.length >= LETTERS.length;
    this.btn['undo']!.disabled = !(cur.sheet || this.pairs.length > 1);
    this.btn['redo']!.disabled = !(cur.sheet || this.pairs.length > 1);
    this.btn['focus-sheet']!.setAttribute('aria-pressed', String(this.focus === 'sheet'));
    this.btn['focus-model']!.setAttribute('aria-pressed', String(this.focus === 'model'));
    this.root.dataset['focus'] = this.focus;
    this.root.dataset['pairs'] = String(cp.length);
    this.invalidate();
  }

  // ---------------------------------------------------------------- accept

  private placementFrom(): SheetPlacement | null {
    const r = this.result();
    if ('error' in r || !this.level) return null;
    const lv = this.level;
    return {
      kind: 'manual', level: { ...(lv.guid ? { storeyGuid: lv.guid } : {}), name: lv.name, elevation: lv.elevation }, plane: 'plan', transform: r.transform,
      ...(r.residual !== undefined ? { residual: r.residual } : {}), source: r.source, pairs: this.completePairs(), ...(r.drawingScale ? { drawingScale: r.drawingScale } : {}),
    };
  }

  private accept(confirmed: boolean): void {
    const sh = this.sheet;
    const p = this.placementFrom();
    if (!sh || !p) return;
    const done = this.ctl.place.apply(sh.id, p, { confirmed });
    if (!done.ok && done.moved) {
      this.pending = p;
      this.confirmText.textContent = `${done.moved} shape${done.moved === 1 ? '' : 's'} on this sheet would move off the elements ${done.moved === 1 ? 'it is' : 'they are'} attached to.`;
      this.update();
      return;
    }
    if (!done.ok) { this.setHint(done.error ?? 'The sheet could not be placed'); return; }
    const id = sh.id;
    this.ctl.overlayOn.add(id);
    this.ctl.closePlace();
    this.ctl.open(id);
  }

  // ---------------------------------------------------------------- drawing

  private invalidate(): void {
    if (this.frame) return;
    this.frame = requestAnimationFrame(() => { this.frame = 0; this.draw(); });
  }

  /** Draw now (scripts and tests). */
  drawNow(): void {
    if (this.frame) { cancelAnimationFrame(this.frame); this.frame = 0; }
    this.draw();
  }

  private draw(): void {
    const sh = this.sheet;
    if (!sh || !this.visible) return;
    fitToChrome(this.root);
    if (this.needFit.sheet && this.sp.stage.clientWidth > 50 && this.sheet) { this.needFit.sheet = false; this.sp.fit([0, 0, sh.widthPt, sh.heightPt]); }
    if (this.needFit.model && this.mp.stage.clientWidth > 50 && this.fitBox) { this.needFit.model = false; this.mp.fit(this.fitBox, true); }
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    // Sheet pane: the page, the overlay preview of the model through the transform, the markers.
    const k = this.sp.scale / this.pageScale;
    this.page.style.width = `${this.page.width}px`;
    this.page.style.height = `${this.page.height}px`;
    this.page.style.transform = `translate(${this.sp.tx}px, ${this.sp.ty}px) scale(${k})`;
    const sW = this.sp.stage.clientWidth, sH = this.sp.stage.clientHeight;
    if (this.ovl.width !== Math.round(sW * dpr) || this.ovl.height !== Math.round(sH * dpr)) {
      this.ovl.width = Math.round(sW * dpr); this.ovl.height = Math.round(sH * dpr);
      this.ovl.style.width = `${sW}px`; this.ovl.style.height = `${sH}px`;
    }
    const og = this.ovl.getContext('2d')!;
    og.setTransform(dpr, 0, 0, dpr, 0, 0);
    og.clearRect(0, 0, sW, sH);
    const r = this.result();
    if (!('error' in r) && this.cut) {
      const fake = { transform: r.transform } as SheetPlacement;
      drawCut(og, this.cut, modelToPixels(fake, (ux, uy) => this.userToSheetPx(ux, uy)), { color: '#d6336c', alpha: 0.85, width: 1.4, view: [0, 0, sW, sH] });
    }
    this.sMarks.textContent = '';
    this.pairs.forEach((p, i) => { if (p.sheet) this.marker(this.sMarks, this.userToSheetPx(p.sheet[0], p.sheet[1]), LETTERS[i]!, '#ffd27a'); });
    // Model pane: the plan cut, the markers, the snap under the pointer.
    const mW = this.mp.stage.clientWidth, mH = this.mp.stage.clientHeight;
    if (this.plan.width !== Math.round(mW * dpr) || this.plan.height !== Math.round(mH * dpr)) {
      this.plan.width = Math.round(mW * dpr); this.plan.height = Math.round(mH * dpr);
      this.plan.style.width = `${mW}px`; this.plan.style.height = `${mH}px`;
    }
    const g = this.plan.getContext('2d')!;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, mW, mH);
    drawCut(g, this.cut, { a: this.mp.scale, b: 0, c: 0, d: -this.mp.scale, e: this.mp.tx, f: this.mp.ty }, { color: '#9fc4ee', alpha: 1, width: 1.3, view: [0, 0, mW, mH] });
    this.mMarks.textContent = '';
    this.pairs.forEach((p, i) => { if (p.model) this.marker(this.mMarks, this.modelPx(p.model[0], p.model[1]), LETTERS[i]!, '#7dd87d'); });
    if (this.hover) {
      const q = this.modelPx(this.hover.snap[0], this.hover.snap[1]);
      this.mMarks.appendChild(svgEl('rect', { x: q[0] - 5, y: q[1] - 5, width: 10, height: 10, fill: 'none', stroke: this.hover.kind === 'corner' ? '#ffd27a' : '#7dd87d', 'stroke-width': 2, 'data-snap': this.hover.kind }));
    }
  }

  private marker(layer: SVGGElement, p: Vec2, letter: string, color: string): void {
    layer.appendChild(svgEl('circle', { cx: p[0], cy: p[1], r: PICK_R, fill: 'rgba(0,0,0,.35)', stroke: color, 'stroke-width': 2 }));
    layer.appendChild(svgEl('line', { x1: p[0] - PICK_R - 4, y1: p[1], x2: p[0] + PICK_R + 4, y2: p[1], stroke: color, 'stroke-width': 1 }));
    layer.appendChild(svgEl('line', { x1: p[0], y1: p[1] - PICK_R - 4, x2: p[0], y2: p[1] + PICK_R + 4, stroke: color, 'stroke-width': 1 }));
    const t = svgEl('text', { x: p[0] + PICK_R + 3, y: p[1] - PICK_R - 2, fill: color, 'font-size': 13, 'font-weight': 700, 'font-family': 'system-ui,sans-serif' });
    t.textContent = letter;
    layer.appendChild(t);
  }

  // ---------------------------------------------------------------- state for scripts and tests

  state(): {
    open: boolean; sheet: string | null; mode: string; focus: string; pairs: Array<{ sheet?: Vec2; model?: Vec2 }>; hint: string; result: string;
    transform: Similarity | null; residual: number | null; level: string | null; canAccept: boolean; sheetView: { scale: number; tx: number; ty: number }; modelView: { scale: number; tx: number; ty: number }; elements: number;
  } {
    const r = this.result();
    return {
      open: this.visible, sheet: this.sheet?.id ?? null, mode: this.mode, focus: this.focus, pairs: this.pairs.map((p) => ({ ...(p.sheet ? { sheet: p.sheet } : {}), ...(p.model ? { model: p.model } : {}) })),
      hint: this.hint.textContent ?? '', result: this.res.textContent ?? '', transform: 'error' in r ? null : r.transform, residual: 'error' in r ? null : r.residual ?? null,
      level: this.level?.name ?? null, canAccept: !('error' in r), sheetView: { scale: this.sp.scale, tx: this.sp.tx, ty: this.sp.ty }, modelView: { scale: this.mp.scale, tx: this.mp.tx, ty: this.mp.ty }, elements: this.cut?.elements.length ?? 0,
    };
  }

  /** Client pixels of a PDF user-space point on the sheet pane, and of plan metres on the model pane (for scripts and tests). */
  clientOfSheet(ux: number, uy: number): Vec2 | null {
    if (!this.sheet) return null;
    const r = this.sp.stage.getBoundingClientRect();
    const [x, y] = this.userToSheetPx(ux, uy);
    return [r.left + x, r.top + y];
  }
  clientOfModel(X: number, Y: number): Vec2 | null {
    if (!this.sheet) return null;
    const r = this.mp.stage.getBoundingClientRect();
    const [x, y] = this.modelPx(X, Y);
    return [r.left + x, r.top + y];
  }
}
