// Live markup on the shared SVG overlay, and the pointer and key handling of the markup tool: drawing (drag, freehand,
// polyline clicks, click to place), select and move, undo / redo / delete / Escape while the drawer is open. Layout comes
// from layout.ts, the same code that burns the markups into the PDF. The orbit does not move while a shape is drawn:
// the capture-phase handlers on the canvas swallow the pointer events of the drawing tools (mouse, touch and pen).

import { getOverlay, svgEl } from '../ui/overlay';
import type { Overlay } from '../ui/overlay';
import { renderOps } from '../bcf/pins';
import { fractionsToPixels, layoutMarkupFull } from './layout';
import type { MarkupLayout } from './layout';
import { distToPolyline, pointInPolygon } from './geometry';
import { newMarkup } from './model';
import type { Markup } from './model';
import { toolInfo } from './controller';
import { buildAttachChip } from './attachUi';
import { markupName } from './layout';
import type { MarkupController, ToolId } from './controller';

const CLICK_SLOP = 5;
const HIT_PX = 14;

function isEditable(t: EventTarget | null): boolean {
  const e = t as HTMLElement | null;
  if (!e || !e.tagName) return false;
  return e.tagName === 'INPUT' || e.tagName === 'TEXTAREA' || e.tagName === 'SELECT' || e.isContentEditable;
}

interface Stroke {
  tool: ToolId;
  pts: Array<[number, number]>;
  id: number;
}

export class MarkupView {
  /** The drawer is open. */
  drawerOpen = false;
  /**
   * The tool takes pointer and key input: while the drawer is open, and also with it closed as long as a drawing tool is
   * chosen (on a phone the drawer covers the view, so you draw with it closed; the floating bar says so and ends it).
   */
  get active(): boolean {
    return this.drawerOpen || this.c.tool !== 'select';
  }
  private cursorSet = false;
  private float: HTMLDivElement | null = null;
  private floatRect: { x: number; y: number; w: number; h: number } | null = null;
  private overlay: Overlay | null = null;
  private layer: SVGGElement | null = null;
  private chip: HTMLButtonElement | null = null;
  /** The attachment chip next to the selected markup (canvas). */
  private attachChip: HTMLDivElement | null = null;
  private attachRect: { x: number; y: number; w: number; h: number } | null = null;
  private chipRect: { x: number; y: number; w: number; h: number } | null = null;
  private stroke: Stroke | null = null;
  private poly: { tool: ToolId; pts: Array<[number, number]>; at: number } | null = null;
  private down: { x: number; y: number; id: number } | null = null;
  private drag: { id: string; sx: number; sy: number; kind: 'shape' | 'box'; from: number[]; off: [number, number]; moved: boolean } | null = null;
  private hits = new Map<string, MarkupLayout['hit']>();
  private last: { x: number; y: number } | null = null;

  constructor(readonly c: MarkupController) {
    const canvas = c.app.canvas;
    canvas.addEventListener('pointerdown', (e) => this.onDown(e), true);
    canvas.addEventListener('pointerup', (e) => this.onUp(e), true);
    canvas.addEventListener('pointermove', (e) => this.onHover(e), true);
    canvas.addEventListener('dblclick', (e) => {
      if (this.active && this.poly) {
        e.stopImmediatePropagation();
        e.preventDefault();
      }
    }, true);
    window.addEventListener('keydown', (e) => this.onKey(e), true);
    c.onChange(() => this.overlay?.invalidate());
    c.cancelDrawing = () => this.cancel();
  }

  get drawing(): boolean {
    return this.stroke !== null || this.poly !== null;
  }
  get polyPoints(): number {
    return this.poly?.pts.length ?? 0;
  }

  /** The drawer opened or closed. */
  setActive(on: boolean): void {
    this.drawerOpen = on;
    if (!on) this.cancel(true);
    this.overlay?.invalidate();
  }

  /** Called per frame by the plugin: create the overlay layer once a model is loaded. */
  tick(): void {
    if (this.overlay || !this.c.app.loaded) return;
    const ov = getOverlay(this.c.app);
    this.overlay = ov;
    this.layer = ov.layer('markup');
    ov.reserve('markup-return', () => this.chipRect);
    ov.reserve('markup-float', () => this.floatRect);
    ov.reserve('markup-attach', () => this.attachRect);
    ov.onUpdate((o) => this.draw(o));
  }

  invalidate(): void {
    this.overlay?.invalidate();
  }

  // ---------------------------------------------------------------- pointer input

  private rel(e: PointerEvent | MouseEvent): [number, number] {
    const r = this.c.app.canvas.getBoundingClientRect();
    return [e.clientX - r.left, e.clientY - r.top];
  }

  private drawingTool(e: PointerEvent): boolean {
    if (!this.active || !this.c.active || this.c.tool === 'select' || !this.c.loaded) return false;
    // Mouse: the primary button draws, the others still orbit and pan. Touch and pen always draw.
    if (e.pointerType === 'mouse' && e.button !== 0) return false;
    return e.isPrimary !== false;
  }

  private onDown(e: PointerEvent): void {
    if (this.c.pickLink && this.c.active && e.button === 0 && e.isPrimary !== false) {
      this.down = { x: e.clientX, y: e.clientY, id: e.pointerId };
      return;
    }
    if (!this.drawingTool(e)) return;
    const tool = this.c.tool;
    const info = toolInfo(tool);
    if (info.how === 'drag' || info.how === 'free') {
      e.stopImmediatePropagation();
      e.preventDefault();
      this.startStroke(e, tool);
    } else if (info.how === 'poly') {
      e.stopImmediatePropagation();
      e.preventDefault();
      this.down = { x: e.clientX, y: e.clientY, id: e.pointerId };
    } else if (info.how === 'click') {
      this.down = { x: e.clientX, y: e.clientY, id: e.pointerId };
    }
  }

  private onUp(e: PointerEvent): void {
    const pl = this.c.pickLink;
    if (pl && this.c.active && e.button === 0 && (this.down || e.pointerType !== 'mouse')) {
      const d0 = this.down;
      this.down = null;
      if (!d0 || Math.hypot(e.clientX - d0.x, e.clientY - d0.y) <= CLICK_SLOP) {
        try { Object.defineProperty(e, 'button', { value: 2 }); } catch { /* the event stays as is */ }
        const [x, y] = this.rel(e);
        const link = this.c.linkAt(pl.kind, x, y);
        if (link) { this.c.pickLink = null; this.c.setAttachment(pl.id, pl.kind, link); this.c.emit(); } else this.c.setStatus(`No ${pl.kind} under the click. Click it again, or press Esc`);
        return;
      }
    }
    const d = this.down;
    if (!d || !this.drawingTool(e)) return;
    this.down = null;
    const info = toolInfo(this.c.tool);
    if (Math.hypot(e.clientX - d.x, e.clientY - d.y) > CLICK_SLOP) return; // an orbit drag
    if (info.how === 'poly') {
      e.stopImmediatePropagation();
      e.preventDefault();
      this.polyClick(this.rel(e));
    } else if (info.how === 'click') {
      // Hide the click from the viewer's select handler (it ignores other buttons); stopping it would starve the controls.
      try {
        Object.defineProperty(e, 'button', { value: 2 });
      } catch {
        /* the event stays as is */
      }
      const [x, y] = this.rel(e);
      this.c.addAnchored(this.c.tool, x, y);
    }
  }

  private onHover(e: PointerEvent): void {
    if (!this.poly) return;
    const [x, y] = this.rel(e);
    this.last = { x, y };
    this.overlay?.invalidate();
  }

  private startStroke(e: PointerEvent, tool: ToolId): void {
    this.cancel(true);
    const pts: Array<[number, number]> = [this.rel(e)];
    this.stroke = { tool, pts, id: e.pointerId };
    const how = toolInfo(tool).how;
    const move = (ev: PointerEvent): void => {
      const st = this.stroke;
      if (!st || ev.pointerId !== st.id) return;
      const q = this.rel(ev);
      if (how === 'drag') st.pts[1] = q;
      else {
        const l = st.pts[st.pts.length - 1]!;
        if (Math.hypot(q[0] - l[0], q[1] - l[1]) >= 2) st.pts.push(q);
      }
      this.overlay?.invalidate();
    };
    const up = (ev: PointerEvent): void => {
      if (this.stroke && ev.pointerId !== this.stroke.id) return;
      window.removeEventListener('pointermove', move, true);
      window.removeEventListener('pointerup', up, true);
      window.removeEventListener('pointercancel', up, true);
      try {
        Object.defineProperty(ev, 'button', { value: 2 });
      } catch {
        /* the event stays as is */
      }
      const st = this.stroke;
      this.stroke = null;
      if (!st || ev.type === 'pointercancel') { this.overlay?.invalidate(); return; }
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const [x, y] of st.pts) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
      if (st.pts.length < 2 || Math.max(x1 - x0, y1 - y0) < 6) {
        this.c.setStatus('Drag further to draw the markup (Esc cancels)');
        return;
      }
      this.c.addShape(st.tool, st.pts);
    };
    window.addEventListener('pointermove', move, true);
    window.addEventListener('pointerup', up, true);
    window.addEventListener('pointercancel', up, true);
    this.cleanupStroke = () => {
      window.removeEventListener('pointermove', move, true);
      window.removeEventListener('pointerup', up, true);
      window.removeEventListener('pointercancel', up, true);
    };
    this.overlay?.invalidate();
  }
  private cleanupStroke: (() => void) | null = null;

  private polyClick(p: [number, number]): void {
    const tool = this.c.tool;
    const now = Date.now();
    if (!this.poly) this.poly = { tool, pts: [], at: 0 };
    const poly = this.poly;
    const last = poly.pts[poly.pts.length - 1];
    // A second tap at the same spot finishes; so does a click on the first corner of a polygon.
    if (last && Math.hypot(p[0] - last[0], p[1] - last[1]) < 6 && now - poly.at < 500) {
      this.finishPoly();
      return;
    }
    if (tool === 'polygon' && poly.pts.length >= 3 && Math.hypot(p[0] - poly.pts[0]![0], p[1] - poly.pts[0]![1]) < 10) {
      this.finishPoly();
      return;
    }
    poly.pts.push(p);
    poly.at = now;
    this.last = { x: p[0], y: p[1] };
    this.c.setStatus(`${poly.pts.length} point${poly.pts.length === 1 ? '' : 's'}. Double click or press Enter to finish (Esc cancels)`);
  }

  /** Finish a polyline or polygon with the corners so far. */
  finishPoly(): boolean {
    const poly = this.poly;
    this.poly = null;
    this.last = null;
    if (!poly) return false;
    const need = poly.tool === 'polygon' ? 3 : 2;
    if (poly.pts.length < need) {
      this.c.setStatus(`A ${poly.tool} needs at least ${need} points`);
      return false;
    }
    this.c.addShape(poly.tool, poly.pts);
    return true;
  }

  /** Cancel a drawing in progress. */
  cancel(quiet = false): boolean {
    const had = this.drawing;
    this.cleanupStroke?.();
    this.cleanupStroke = null;
    this.stroke = null;
    this.poly = null;
    this.down = null;
    this.last = null;
    if (had && !quiet) this.c.setStatus('Drawing cancelled');
    this.overlay?.invalidate();
    return had;
  }

  // ---------------------------------------------------------------- keys

  private onKey(e: KeyboardEvent): void {
    if (!this.active || !this.c.active) return;
    const editing = isEditable(e.target);
    const mod = e.ctrlKey || e.metaKey;
    if (e.key === 'Escape') {
      if (this.c.pickLink || this.c.attachMenuOpen) {
        e.stopImmediatePropagation(); e.preventDefault();
        this.c.pickLink = null;
        this.c.attachMenuOpen = null;
        this.c.emit();
        return;
      }
      if (this.cancel()) { e.stopImmediatePropagation(); e.preventDefault(); return; }
      if (this.c.tool !== 'select') { e.stopImmediatePropagation(); e.preventDefault(); this.c.setTool('select'); return; }
      if (this.c.selected) { e.stopImmediatePropagation(); e.preventDefault(); this.c.selectMarkup(null); }
      return;
    }
    if (editing) return;
    if (mod && !e.altKey && (e.key === 'z' || e.key === 'Z')) {
      e.stopImmediatePropagation();
      e.preventDefault();
      if (e.shiftKey) this.c.redo(); else this.c.undo();
    } else if (mod && !e.altKey && (e.key === 'y' || e.key === 'Y')) {
      e.stopImmediatePropagation();
      e.preventDefault();
      this.c.redo();
    } else if (e.key === 'Enter' && this.poly) {
      e.stopImmediatePropagation();
      e.preventDefault();
      this.finishPoly();
    } else if ((e.key === 'Delete' || e.key === 'Backspace') && this.c.selected && !mod) {
      e.stopImmediatePropagation();
      e.preventDefault();
      this.c.remove(this.c.selected);
    }
  }

  // ---------------------------------------------------------------- drawing on the overlay

  private ensureChip(): HTMLButtonElement | null {
    if (this.chip) return this.chip;
    const stage = this.c.app.canvas.parentElement;
    if (!stage) return null;
    const b = document.createElement('button');
    b.type = 'button';
    b.id = 'markup-return';
    b.textContent = 'Return to markup view';
    b.setAttribute('aria-label', 'Return to markup view');
    b.style.cssText = 'position:absolute;top:44px;left:50%;transform:translateX(-50%);z-index:8;display:none;padding:6px 12px;border-radius:14px;border:1px solid #3b9cff;background:#14365c;color:#eaf2ff;font:600 12px system-ui,sans-serif;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,0.35)';
    b.addEventListener('click', () => {
      const s = this.c.active;
      if (s) this.c.restore(s.id, true);
    });
    stage.appendChild(b);
    this.chip = b;
    return b;
  }

  /** Centre an element in the free part of the view (clear of the rails and drawer) and cap its width. */
  private place(e: HTMLElement, edge: 'top' | 'bottom'): void {
    const ov = this.overlay;
    if (!ov) return;
    const ins = ov.insets;
    e.style.left = `${(ins.left + ov.width - ins.right) / 2}px`;
    e.style.maxWidth = `${Math.max(120, ov.width - ins.left - ins.right - 16)}px`;
    if (edge === 'bottom') e.style.bottom = `${ins.bottom + 8}px`;
    else e.style.top = `${ins.top + 8}px`;
  }

  /** The floating bar for a drawing tool that stays on with the drawer closed: what is drawn, undo, redo, done, tools. */
  private updateFloat(): void {
    const c = this.c;
    const show = !this.drawerOpen && c.tool !== 'select' && !!c.active && c.loaded;
    if (!show) {
      if (this.float) this.float.style.display = 'none';
      this.floatRect = null;
      return;
    }
    const stage = c.app.canvas.parentElement;
    if (!stage) return;
    if (!this.float) {
      const f = document.createElement('div');
      f.id = 'markup-float';
      f.style.cssText = 'position:absolute;left:50%;bottom:44px;transform:translateX(-50%);z-index:8;display:flex;flex-wrap:wrap;justify-content:center;gap:6px;align-items:center;padding:6px 8px;border-radius:18px;width:max-content;border:1px solid #3b9cff;background:#14202e;color:#eaf2ff;font:600 12px system-ui,sans-serif;box-shadow:0 2px 8px rgba(0,0,0,0.35);max-width:calc(100% - 16px);box-sizing:border-box';
      const mk = (label: string, act: string, fn: () => void): HTMLButtonElement => {
        const b = document.createElement('button');
        b.type = 'button';
        b.textContent = label;
        b.setAttribute('data-act', act);
        b.style.cssText = 'border:1px solid #3b6c9c;background:#1c2f45;color:#eaf2ff;border-radius:12px;padding:5px 10px;font:inherit;cursor:pointer;min-height:30px';
        b.addEventListener('click', fn);
        return b;
      };
      const label = document.createElement('span');
      label.setAttribute('data-act', 'label');
      f.append(label, mk('Undo', 'undo', () => c.undo()), mk('Redo', 'redo', () => c.redo()), mk('Finish', 'finish', () => this.finishPoly()), mk('Done', 'done', () => c.setTool('select')), mk('Tools', 'tools', () => window.__xrayToolbar?.open('markup')));
      stage.appendChild(f);
      this.float = f;
    }
    const f = this.float;
    f.style.display = 'flex';
    this.place(f, 'bottom');
    f.querySelector<HTMLElement>('[data-act=label]')!.textContent = toolInfo(c.tool).label;
    f.querySelector<HTMLElement>('[data-act=finish]')!.style.display = this.polyPoints > 0 ? '' : 'none';
    f.querySelector<HTMLButtonElement>('[data-act=undo]')!.disabled = !c.canUndo;
    f.querySelector<HTMLButtonElement>('[data-act=redo]')!.disabled = !c.canRedo;
    const r = f.getBoundingClientRect();
    const cr = c.app.canvas.getBoundingClientRect();
    this.floatRect = { x: r.left - cr.left, y: r.top - cr.top, w: r.width, h: r.height };
  }

  /** The attachment chip next to the selected shape: its words and the Change menu. Hidden when nothing is selected. */
  private updateAttachChip(ov: Overlay, set: import('./model').MarkupSet | null, box: { x0: number; y0: number; x1: number; y1: number } | null): void {
    const sel = set && this.c.selected ? set.markups.find((m) => m.id === this.c.selected) : undefined;
    const stage = this.c.app.canvas.parentElement;
    if (!sel || !box || !stage) {
      if (this.attachChip) { this.attachChip.style.display = 'none'; this.attachChip.textContent = ''; }
      this.attachRect = null;
      return;
    }
    if (!this.attachChip) {
      const d = document.createElement('div');
      d.id = 'markup-attach-chip';
      d.style.cssText = 'position:absolute;z-index:8;pointer-events:auto;max-width:calc(100% - 16px)';
      stage.appendChild(d);
      this.attachChip = d;
    }
    const d = this.attachChip;
    d.style.display = '';
    d.textContent = '';
    d.appendChild(buildAttachChip(this.c, sel, 'canvas'));
    const ins = ov.insets;
    const w = d.offsetWidth || 220;
    const h = d.offsetHeight || 22;
    const left = Math.min(Math.max(ins.left + 4, box.x0), Math.max(ins.left + 4, ov.width - ins.right - w - 4));
    const top = Math.min(Math.max(ins.top + 4, box.y1 + 12), Math.max(ins.top + 4, ov.height - ins.bottom - h - 4));
    d.style.left = `${left}px`;
    d.style.top = `${top}px`;
    this.attachRect = { x: left, y: top, w, h };
  }

  private tmpMarkup(tool: ToolId, pts: Array<[number, number]>, W: number, H: number): Markup | null {
    const info = toolInfo(tool);
    if (!info.kind || pts.length < 2) return null;
    const p = info.how === 'drag' ? [pts[0]!, pts[pts.length - 1]!] : pts;
    return newMarkup(info.kind, {
      id: 'preview', number: this.c.active?.nextNumber ?? 1, author: '', colour: this.c.colour(tool), weight: this.c.weight, fill: this.c.fill,
      shape: { points: p.map(([x, y]) => [x / W, y / H] as [number, number]), depth: 1 },
    });
  }

  private draw(ov: Overlay): void {
    const layer = this.layer;
    if (!layer) return;
    layer.textContent = '';
    this.hits.clear();
    const set = this.c.active;
    const chip = this.ensureChip();
    this.updateFloat();
    const want = this.active && this.c.tool !== 'select' && !!set;
    if (want !== this.cursorSet) {
      this.c.app.canvas.style.cursor = want ? 'crosshair' : '';
      this.cursorSet = want;
    }
    if (!this.c.loaded || !set || !this.c.visible) {
      if (chip) chip.style.display = 'none';
      this.chipRect = null;
      this.updateAttachChip(ov, null, null);
      return;
    }
    const ctx = this.c.layoutContext(set, ov.width, ov.height, { insets: ov.insets, reserved: ov.reserved, behind: (k, pts) => this.c.behindCache.behind(k, pts) });
    const faded = this.c.away();
    const lock = this.c.lockState(set);
    const interactive = this.drawerOpen && this.c.tool === 'select';
    let selBox: { x0: number; y0: number; x1: number; y1: number } | null = null;
    for (const m of set.markups) {
      const L = layoutMarkupFull(m, ctx, { selected: m.id === this.c.selected, faded, ...(lock ? { lock } : {}) });
      if (!L.ops.length) continue;
      const g = svgEl('g', { 'data-mk': m.id, 'data-number': String(m.number) });
      renderOps(g, L.ops);
      layer.appendChild(g);
      this.hits.set(m.id, L.hit);
      if (L.behind) {
        g.setAttribute('data-behind', '1');
        const t = svgEl('title');
        t.textContent = `${markupName(m)}: behind other geometry from here`;
        g.appendChild(t);
      }
      if (interactive) this.wire(g, m, L, ctx);
      // The pin a view-locked shape collapses to: always clickable, flies to the view the markup was made in.
      const pins = Array.from(g.querySelectorAll<SVGElement>('[data-role="pin"]'));
      if (pins.length) {
        const t = svgEl('title');
        t.textContent = `${markupName(m)}${m.text ? `: ${m.text.slice(0, 60)}` : ''}. Click to go to the view it was made in`;
        g.appendChild(t);
        g.setAttribute('data-mk-pin', m.id);
        for (const el of pins) {
          el.style.pointerEvents = 'all';
          el.style.cursor = 'pointer';
          el.addEventListener('pointerdown', (e: PointerEvent) => e.stopPropagation());
          el.addEventListener('click', (e: MouseEvent) => { e.stopPropagation(); this.c.selectMarkup(m.id); this.c.restore(set.id, true); });
        }
      }
      if (m.id === this.c.selected && L.hit && L.hit.pts.length >= 4 && !pins.length) {
        let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
        for (let i = 0; i < L.hit.pts.length; i += 2) { x0 = Math.min(x0, L.hit.pts[i]!); x1 = Math.max(x1, L.hit.pts[i]!); y0 = Math.min(y0, L.hit.pts[i + 1]!); y1 = Math.max(y1, L.hit.pts[i + 1]!); }
        selBox = { x0, y0, x1, y1 };
      }
    }
    this.updateAttachChip(ov, set, selBox);
    // The drawing in progress, drawn by the same layout (fractions of the canvas, drawn direct).
    const st = this.stroke;
    const pl = this.poly;
    const W = ov.width;
    const H = ov.height;
    let prev: Markup | null = null;
    if (st && st.pts.length > 1) prev = this.tmpMarkup(st.tool, st.pts, W, H);
    else if (pl) {
      const pts = [...pl.pts];
      if (this.last) pts.push([this.last.x, this.last.y]);
      prev = this.tmpMarkup(pl.tool, pts, W, H);
      for (const [x, y] of pl.pts) layer.appendChild(svgEl('circle', { cx: x, cy: y, r: 3.5, fill: '#ffffff', stroke: '#3b9cff', 'stroke-width': 1.5 }));
    }
    if (prev) {
      const g = svgEl('g', { 'data-mk-preview': prev.kind });
      renderOps(g, layoutMarkupFull(prev, { ...ctx, shapeDirect: true }).ops.filter((o) => o.role !== 'badge'));
      layer.appendChild(g);
    }
    // The "Return to markup view" chip.
    if (chip) {
      const away = faded;
      chip.style.display = away ? '' : 'none';
      if (away) {
        this.place(chip, 'top');
        const r = chip.getBoundingClientRect();
        const c = this.c.app.canvas.getBoundingClientRect();
        this.chipRect = { x: r.left - c.left, y: r.top - c.top, w: r.width, h: r.height };
      } else this.chipRect = null;
    }
  }

  /** Pointer handlers of a markup in the select tool: click selects, drag moves the shape or the text box. */
  private wire(g: SVGGElement, m: Markup, L: MarkupLayout, ctx: ReturnType<MarkupController['layoutContext']>): void {
    const grab = (el: SVGElement, kind: 'shape' | 'box'): void => {
      el.style.pointerEvents = 'all';
      el.style.cursor = 'move';
      el.addEventListener('pointerdown', (e: PointerEvent) => this.startDrag(e as PointerEvent, m, kind, ctx));
    };
    for (const el of Array.from(g.querySelectorAll<SVGElement>('[data-role="box"], [data-role="badge"], [data-role="anchor"]'))) grab(el, m.shape ? 'shape' : 'box');
    if (L.hit) {
      const { pts, closed, filled } = L.hit;
      const hit = svgEl(closed ? 'polygon' : 'polyline', { points: pts.map((v) => v.toFixed(1)).join(' '), fill: filled ? 'rgba(0,0,0,0)' : 'none', stroke: 'rgba(0,0,0,0)', 'stroke-width': HIT_PX, 'stroke-linejoin': 'round' });
      hit.setAttribute('data-hit', m.id);
      grab(hit, m.shape ? 'shape' : 'box');
      hit.style.pointerEvents = filled ? 'all' : 'stroke';
      g.appendChild(hit);
    }
    // Anchored markups drag by their lines too.
    if (!m.shape) for (const el of Array.from(g.querySelectorAll<SVGElement>('[data-role="line"]'))) grab(el, 'box');
  }

  private startDrag(e: PointerEvent, m: Markup, kind: 'shape' | 'box', ctx: ReturnType<MarkupController['layoutContext']>): void {
    if (e.button !== 0 && e.pointerType === 'mouse') return;
    e.stopPropagation();
    e.preventDefault();
    this.c.selectMarkup(m.id);
    const from = m.shape ? (fractionsToPixels(m.shape.points, m.shape.depth, ctx) ?? []) : [];
    this.drag = { id: m.id, sx: e.clientX, sy: e.clientY, kind, from, off: m.offset ? [...m.offset] : [0, 0], moved: false };
    const h = Math.max(1, this.overlay?.height ?? 1);
    const pts: Array<[number, number]> = [];
    for (let i = 0; i < from.length; i += 2) pts.push([from[i]!, from[i + 1]!]);
    const move = (ev: PointerEvent): void => {
      const d = this.drag;
      if (!d) return;
      const dx = ev.clientX - d.sx;
      const dy = ev.clientY - d.sy;
      if (!d.moved && Math.hypot(dx, dy) < 3) return;
      const f = this.c.markup(d.id);
      if (!f) return;
      if (!d.moved) { d.moved = true; this.c.record(f.set); }
      if (d.kind === 'shape') this.c.moveShape(d.id, pts, dx, dy);
      else this.c.patch(d.id, { offset: [d.off[0] + dx / h, d.off[1] + dy / h] }, { quiet: true });
    };
    const up = (): void => {
      window.removeEventListener('pointermove', move, true);
      window.removeEventListener('pointerup', up, true);
      window.removeEventListener('pointercancel', up, true);
      const d = this.drag;
      this.drag = null;
      if (d?.moved) { if (d.kind === 'shape') this.c.reattach(d.id); this.c.emit(); }
    };
    window.addEventListener('pointermove', move, true);
    window.addEventListener('pointerup', up, true);
    window.addEventListener('pointercancel', up, true);
  }

  /** The markup under a canvas point, topmost first (scripts and tests). */
  hitTest(x: number, y: number): string | null {
    const set = this.c.active;
    if (!set) return null;
    for (let i = set.markups.length - 1; i >= 0; i--) {
      const m = set.markups[i]!;
      const h = this.hits.get(m.id);
      if (!h) continue;
      if (h.closed && h.filled && pointInPolygon(x, y, h.pts)) return m.id;
      if (distToPolyline(x, y, h.pts, h.closed) <= HIT_PX / 2) return m.id;
    }
    return null;
  }
}
