// Measure tool (point to point and element to element). Points come from camera rays against the merged-geometry BVH
// (first visible surface), snap to the nearest vertex of the hit triangle within 12 px, and are drawn on the shared SVG
// overlay as dimension lines with labels. See docs-features/measure.md.

import type GUI from 'lil-gui';
import type { AppPlugin, ViewerApp } from '../app';
import { registerAction } from '../input/actions';
import { distance, formatLength, MEASURE_CSV_HEADER, measurementRows, snapToVertex, UNITS } from '../measure/maths';
import type { Measurement, Units, V3 } from '../measure/maths';
import { cameraRay, elementDistance, firstSurfaceHit } from '../measure/geometry';
import type { SurfaceHit } from '../measure/geometry';
import { downloadText, toCsv } from '../tools/csv';
import { ICONS } from '../tools/icons';
import { registerTool } from '../tools/registry';
import { button, check, note, row, select, statusLine } from '../tools/ui';
import { el } from '../ui/dom';
import { ClearanceTool, clearancePanel } from '../measure/clearanceTool';
import { getOverlay, svgEl } from '../ui/overlay';
import type { Overlay, ScreenPoint } from '../ui/overlay';
import { registerParamSection } from '../ui/params';

export const MEASURE_MODES = ['point to point', 'element to element'] as const;
export type MeasureMode = (typeof MEASURE_MODES)[number];
const SNAP_PX = 12;
const CLICK_SLOP = 5;

interface Pending {
  point: V3;
  element: number;
}

class MeasureTool {
  opts = { mode: 'point to point' as MeasureMode, units: 'm' as Units, snap: true };
  readonly list: Measurement[] = [];
  /** The drawer is open: clicks on the canvas measure. */
  active = false;
  pending: Pending | null = null;
  private hover: { point: V3; snapped: boolean; element: number } | null = null;
  private nextId = 1;
  private overlay: Overlay | null = null;
  private layer: SVGGElement | null = null;
  private escHandler: ((e: KeyboardEvent) => void) | null = null;
  private listeners = new Set<() => void>();
  private folder: GUI | null = null;
  private down: { x: number; y: number } | null = null;
  message = '';
  /** Redraw after a setting changed. */
  refresh: () => void = () => undefined;

  constructor(readonly app: ViewerApp) {
    const c = app.canvas;
    // Capture phase on the canvas itself: runs before the viewer's own click-to-select handler.
    c.addEventListener('pointerdown', (e) => {
      this.down = { x: e.clientX, y: e.clientY };
    }, true);
    c.addEventListener('pointerup', (e) => this.onPointerUp(e), true);
    c.addEventListener('pointermove', (e) => this.onPointerMove(e), true);
    c.addEventListener('pointerleave', () => {
      if (this.hover) {
        this.hover = null;
        this.overlay?.invalidate();
      }
    });
  }

  attach(f: GUI): void {
    this.folder = f;
  }

  onChange(cb: () => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  emit(): void {
    this.overlay?.invalidate();
    for (const l of this.listeners) l();
    this.folder?.controllersRecursive().forEach((c) => c.updateDisplay());
  }

  ensureOverlay(): void {
    if (this.overlay) return;
    this.overlay = getOverlay(this.app);
    this.layer = this.overlay.layer('measure');
    this.overlay.onUpdate((ov) => this.draw(ov));
  }

  // ---------------------------------------------------------------- mode

  setActive(on: boolean): void {
    this.active = on;
    this.app.canvas.style.cursor = on ? 'crosshair' : '';
    if (!on) this.cancelPending();
    this.hover = null;
    this.emit();
  }

  setMode(m: MeasureMode): void {
    this.opts.mode = m;
    this.cancelPending();
    this.message = '';
    this.emit();
  }

  cancelPending(): void {
    if (!this.pending) return;
    this.pending = null;
    this.removeEsc();
    this.message = '';
    this.emit();
  }

  private addEsc(): void {
    if (this.escHandler) return;
    // window capture runs before the toolbar's document capture handler, so the first Escape cancels the pending point
    // and only the next one closes the drawer.
    this.escHandler = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || !this.pending) return;
      e.stopImmediatePropagation();
      e.preventDefault();
      this.cancelPending();
    };
    window.addEventListener('keydown', this.escHandler, true);
  }

  private removeEsc(): void {
    if (!this.escHandler) return;
    window.removeEventListener('keydown', this.escHandler, true);
    this.escHandler = null;
  }

  // ---------------------------------------------------------------- picking

  /** Surface point under a client position, snapped when enabled. null on a miss. */
  pickAt(clientX: number, clientY: number): { point: V3; snapped: boolean; element: number } | null {
    const app = this.app;
    const loaded = app.loaded;
    if (!loaded) return null;
    const r = app.canvas.getBoundingClientRect();
    const px = clientX - r.left;
    const py = clientY - r.top;
    const cam = app.renderer.camera;
    cam.updateMatrixWorld();
    const ray = cameraRay(cam, (px / r.width) * 2 - 1, -((py / r.height) * 2 - 1));
    const hides = app.controller.settings.overrides.userHides;
    const alpha = app.renderer.state.alpha;
    const hit: SurfaceHit | null = firstSurfaceHit(loaded.geometry, ray, (id) => hides.has(id) || (alpha[id] ?? 1) < 0);
    if (!hit) return null;
    const p: V3 = [hit.point.x, hit.point.y, hit.point.z];
    if (!this.opts.snap) return { point: p, snapped: false, element: hit.element };
    this.ensureOverlay();
    const ov = this.overlay!;
    const tmp: ScreenPoint = { x: 0, y: 0, visible: false, front: false, depth: 0 };
    const s = snapToVertex(p, hit.triangle, { x: px, y: py }, (v) => ov.project(v, tmp), SNAP_PX);
    return { point: s.point, snapped: s.snapped, element: hit.element };
  }

  private onPointerMove(e: PointerEvent): void {
    if (!this.active || e.buttons !== 0) return;
    const h = this.pickAt(e.clientX, e.clientY);
    this.hover = h;
    this.overlay?.invalidate();
  }

  private onPointerUp(e: PointerEvent): void {
    if (!this.active || e.button !== 0 || !this.down) return;
    const moved = Math.hypot(e.clientX - this.down.x, e.clientY - this.down.y);
    this.down = null;
    if (moved > CLICK_SLOP) return; // an orbit drag
    // The click measures instead of selecting. The viewer's own click-to-select handler ignores anything but button 0, so
    // present this event to the later listeners as a secondary button; stopping it instead would starve OrbitControls
    // of its pointerup and leave it in the rotate state.
    try {
      Object.defineProperty(e, 'button', { value: 2 });
    } catch {
      /* the event stays as is */
    }
    const h = this.pickAt(e.clientX, e.clientY);
    if (!h) {
      this.message = 'No surface under the cursor';
      this.emit();
      return;
    }
    this.click(h.point, h.element);
  }

  /** The two-click state machine (also used by tests and scripts). */
  click(point: V3, element: number): void {
    this.ensureOverlay();
    if (!this.pending) {
      this.pending = { point, element };
      this.message = this.opts.mode === 'point to point' ? 'Click the second point (Esc cancels)' : `Click the second element (first: ${this.nameOf(element)}; Esc cancels)`;
      this.addEsc();
      this.emit();
      return;
    }
    const first = this.pending;
    this.pending = null;
    this.removeEsc();
    if (this.opts.mode === 'point to point') {
      this.add({ id: 0, kind: 'point', a: [...first.point], b: [...point], distance: distance(first.point, point) });
    } else {
      this.measureElements(first.element, element);
    }
  }

  private measureElements(a: number, b: number): void {
    const loaded = this.app.loaded;
    const geo = this.app.geometry;
    if (!loaded || !geo) return;
    if (a === b) {
      this.message = 'Pick two different elements';
      this.emit();
      return;
    }
    const t0 = performance.now();
    const r = elementDistance(loaded.geometry, a, b, (x, y) => geo.intersects(x, y));
    if (!r) {
      this.message = 'One of the elements has no geometry';
      this.emit();
      return;
    }
    this.add({ id: 0, kind: 'element', a: r.a, b: r.b, distance: r.distance, elementA: a, elementB: b });
    this.message = `${r.touching ? 'Elements touch or overlap' : 'Closest points found'} (${(performance.now() - t0).toFixed(0)} ms)`;
    this.emit();
  }

  add(m: Measurement): void {
    m.id = this.nextId++;
    this.list.push(m);
    this.message = `${m.kind === 'point' ? 'Distance' : 'Minimum distance'} ${formatLength(m.distance, this.opts.units)}`;
    this.emit();
  }

  remove(id: number): void {
    const i = this.list.findIndex((m) => m.id === id);
    if (i >= 0) this.list.splice(i, 1);
    this.emit();
  }

  clear(): void {
    this.list.length = 0;
    this.cancelPending();
    this.message = '';
    this.emit();
  }

  onModel(): void {
    this.list.length = 0;
    this.pending = null;
    this.removeEsc();
    this.hover = null;
    this.emit();
  }

  nameOf = (id: number): string => {
    const e = this.app.controller.model.elements[id];
    return e ? (e.name && e.name.trim() ? e.name : `${e.ifcClass.replace(/^Ifc/, '')} #${id}`) : `#${id}`;
  };

  exportCsv(): number {
    const shift = this.app.controller.model.originShift;
    const rows = measurementRows(this.list, shift, (id) => this.app.controller.model.elements[id]?.globalId ?? String(id));
    downloadText(`measurements-${this.app.modelName}.csv`, toCsv(MEASURE_CSV_HEADER, rows));
    return rows.length;
  }

  // ---------------------------------------------------------------- drawing

  private draw(ov: Overlay): void {
    const layer = this.layer;
    if (!layer) return;
    layer.textContent = '';
    const sa: ScreenPoint = { x: 0, y: 0, visible: false, front: false, depth: 0 };
    const sb: ScreenPoint = { x: 0, y: 0, visible: false, front: false, depth: 0 };
    const units = this.opts.units;

    const dimension = (a: V3, b: V3, text: string, colour: string, dashed = false): void => {
      ov.project(a, sa);
      ov.project(b, sb);
      if (!sa.front && !sb.front) return;
      const g = svgEl('g');
      if (sa.front && sb.front) {
        for (const [w, c] of [[4, 'rgba(10,14,20,0.75)'], [2, colour]] as const) {
          const l = svgEl('line', { x1: sa.x, y1: sa.y, x2: sb.x, y2: sb.y, stroke: c, 'stroke-width': w, 'stroke-linecap': 'round' });
          if (dashed && w === 2) l.setAttribute('stroke-dasharray', '5 4');
          g.appendChild(l);
        }
        for (const s of [sa, sb]) g.appendChild(svgEl('circle', { cx: s.x, cy: s.y, r: 4, fill: colour, stroke: '#0b0f14', 'stroke-width': 1.5 }));
        const mx = (sa.x + sb.x) / 2;
        const my = (sa.y + sb.y) / 2;
        const w = text.length * 6.6 + 12;
        g.appendChild(svgEl('rect', { x: mx - w / 2, y: my - 20, width: w, height: 18, rx: 4, fill: 'rgba(14,18,24,0.88)', stroke: colour, 'stroke-width': 1 }));
        const t = svgEl('text', { x: mx, y: my - 7, 'text-anchor': 'middle', fill: '#f2f6fb', 'font-size': 12, 'font-family': 'ui-monospace,Menlo,Consolas,monospace' });
        t.setAttribute('data-measure-label', '1');
        t.textContent = text;
        g.appendChild(t);
      }
      layer.appendChild(g);
    };

    for (const m of this.list) {
      dimension(m.a, m.b, formatLength(m.distance, units), m.kind === 'point' ? '#ffd23f' : '#4ee0b4');
    }

    const dot = (p: V3, colour: string, square = false): void => {
      ov.project(p, sa);
      if (!sa.front) return;
      layer.appendChild(square
        ? svgEl('rect', { x: sa.x - 5, y: sa.y - 5, width: 10, height: 10, fill: colour, stroke: '#0b0f14', 'stroke-width': 1.5 })
        : svgEl('circle', { cx: sa.x, cy: sa.y, r: 5, fill: colour, stroke: '#0b0f14', 'stroke-width': 1.5 }));
    };

    if (this.active && this.pending) {
      dot(this.pending.point, '#ffffff', this.opts.mode === 'element to element');
      if (this.hover && this.opts.mode === 'point to point') {
        dimension(this.pending.point, this.hover.point, formatLength(distance(this.pending.point, this.hover.point), units), '#ffffff', true);
      }
    }
    if (this.active && this.hover) {
      ov.project(this.hover.point, sa);
      if (sa.front) {
        if (this.hover.snapped) layer.appendChild(svgEl('circle', { cx: sa.x, cy: sa.y, r: 8, fill: 'none', stroke: '#ffd23f', 'stroke-width': 2, 'data-snap': '1' }));
        else layer.appendChild(svgEl('circle', { cx: sa.x, cy: sa.y, r: 3, fill: '#ffffff', stroke: '#0b0f14', 'stroke-width': 1 }));
      }
    }
  }
}

let tool: MeasureTool | null = null;
let clearance: ClearanceTool | null = null;

function panel(box: HTMLElement, app: ViewerApp): (() => void) | void {
  const t = tool;
  if (!t) return;
  t.ensureOverlay();
  t.setActive(true);
  const mode = select<MeasureMode>('mode', MEASURE_MODES, () => t.opts.mode, (v) => t.setMode(v));
  const units = select<Units>('units', UNITS, () => t.opts.units, (v) => { t.opts.units = v; t.refresh(); });
  const snap = check('Snap to vertices (12 px)', () => t.opts.snap, (v) => { t.opts.snap = v; });
  const status = statusLine();
  const list = el('div', 'xt-list');
  const exportBtn = button('Export CSV', () => status.set(`Exported ${t.exportCsv()} measurements`), { title: 'Download the measurements as CSV (IFC world coordinates)' });
  const clearBtn = button('Clear', () => t.clear(), { title: 'Delete all measurements' });
  box.append(mode.root, units.root, snap.root, row(exportBtn, clearBtn), status, list,
    note('Click two points on surfaces. Esc cancels the pending point; Esc again closes this panel. Closing the panel keeps the measurements on screen.'));
  const refresh = (): void => {
    mode.update(); units.update(); snap.update();
    status.set(t.message || (t.opts.mode === 'point to point' ? 'Click the first point' : 'Click the first element'));
    list.textContent = '';
    for (const m of t.list) {
      const item = el('div', 'xt-item', { 'data-measure': String(m.id) });
      const label = m.kind === 'element' ? `${t.nameOf(m.elementA!)} ↔ ${t.nameOf(m.elementB!)}` : 'point to point';
      item.append(
        el('span', undefined, undefined, `#${m.id}`),
        el('span', 'grow', { title: label }, label),
        el('strong', undefined, undefined, formatLength(m.distance, t.opts.units)),
      );
      const x = el('button', 'x', { type: 'button', 'aria-label': `Delete measurement ${m.id}`, title: 'Delete' }, '×');
      x.addEventListener('click', () => t.remove(m.id));
      item.appendChild(x);
      list.appendChild(item);
    }
    if (t.list.length === 0) list.appendChild(el('div', 'xt-note', undefined, 'No measurements yet.'));
    exportBtn.setDisabled(t.list.length === 0 ? 'Nothing to export' : false);
    clearBtn.setDisabled(t.list.length === 0 ? 'Nothing to clear' : false);
  };
  refresh();
  const off = t.onChange(refresh);
  void app;
  return () => {
    off();
    t.setActive(false);
  };
}

export const measurePlugin: AppPlugin = {
  name: 'measure',

  install(app: ViewerApp): void {
    const t = new MeasureTool(app);
    tool = t;
    t.refresh = () => t.emit();
    registerTool({
      id: 'measure', label: 'Measure', title: 'Distance between two points or two elements', icon: ICONS.measure, order: 70,
      panel: (box, a) => panel(box, a), isActive: () => t.active,
    });
    const c = new ClearanceTool(app);
    clearance = c;
    registerTool({
      id: 'clearance', label: 'Clearance', title: 'Colour context elements by distance to the focus: clash, tight, ok', icon: ICONS.clearance, order: 80,
      panel: (box) => clearancePanel(box, c), toggle: (_a, on) => c.setEnabled(on), isActive: () => c.enabled,
    });
    registerAction({ id: 'clearance.toggle', label: 'Clearance: toggle colouring', group: 'Tools', keys: [], run: () => c.setEnabled(!c.enabled) });
    registerParamSection('clearance', {
      collect: () => ({ tight: c.settings.tight, max: c.settings.max }),
      apply(value, bad, path) {
        if (!value || typeof value !== 'object') { bad.push(path); return; }
        const v = value as Record<string, unknown>;
        for (const k of ['tight', 'max'] as const) {
          if (v[k] === undefined) continue;
          if (typeof v[k] === 'number' && Number.isFinite(v[k] as number) && (v[k] as number) > 0) c.settings[k] = v[k] as number;
          else bad.push(`${path}.${k}`);
        }
        if (c.settings.max < c.settings.tight) c.settings.max = c.settings.tight;
        c.settingsChanged();
      },
    });
    (window as unknown as { __xrayClearance?: unknown }).__xrayClearance = {
      get enabled() { return c.enabled; },
      get counts() { return c.lastCounts; },
      get status() { return c.status; },
      get settings() { return c.settings; },
      setEnabled: (on: boolean) => c.setEnabled(on),
      recompute: () => c.recompute(),
    };
    registerAction({
      id: 'measure.clear', label: 'Measure: clear measurements', group: 'Tools', keys: [], run: () => t.clear(),
    });

    registerParamSection('measure', {
      collect: () => ({ units: t.opts.units, snap: t.opts.snap, mode: t.opts.mode }),
      apply(value, bad, path) {
        if (!value || typeof value !== 'object') { bad.push(path); return; }
        const v = value as Record<string, unknown>;
        if (v['units'] !== undefined) {
          if ((UNITS as readonly unknown[]).includes(v['units'])) t.opts.units = v['units'] as Units;
          else bad.push(`${path}.units`);
        }
        if (v['snap'] !== undefined) {
          if (typeof v['snap'] === 'boolean') t.opts.snap = v['snap'];
          else bad.push(`${path}.snap`);
        }
        if (v['mode'] !== undefined) {
          if ((MEASURE_MODES as readonly unknown[]).includes(v['mode'])) t.opts.mode = v['mode'] as MeasureMode;
          else bad.push(`${path}.mode`);
        }
        t.refresh();
      },
    });

    (window as unknown as { __xrayMeasure?: unknown }).__xrayMeasure = {
      get list() { return t.list; },
      get pending() { return t.pending; },
      click: (point: V3, element: number) => t.click(point, element),
      pickAt: (x: number, y: number) => t.pickAt(x, y),
      clear: () => t.clear(),
    };

    const gui = app.panel;
    if (gui) {
      const f = gui.addFolder('Measure');
      f.close();
      t.attach(f);
      f.add(t.opts, 'mode', [...MEASURE_MODES]).name('mode').onChange((v: MeasureMode) => t.setMode(v));
      f.add(t.opts, 'units', [...UNITS]).name('units').onChange(() => t.refresh());
      f.add(t.opts, 'snap').name('snap to vertices');
      f.add({ clear: () => t.clear() }, 'clear').name('Clear measurements');

      const fc = gui.addFolder('Clearance');
      fc.close();
      c.attach(fc);
      fc.add(c, 'enabled').name('enabled').onChange((v: boolean) => c.setEnabled(v));
      fc.add(c.settings, 'tight', 0.005, 0.5, 0.005).name('tight (m)').onChange(() => c.settingsChanged());
      fc.add(c.settings, 'max', 0.05, 5, 0.05).name('max range (m)').onChange(() => c.settingsChanged());
      fc.add(c, 'status').name('Clearance status').disable();
    }
  },

  onModel(): void {
    tool?.onModel();
    clearance?.onModel();
  },

  onStatic(): void {
    clearance?.onStatic();
  },
};
