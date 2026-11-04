// Clearance tool: colours context elements by their minimum surface distance to the current focus set (see clearance.ts
// for the bands). Writes preview colours into renderer.state.color and restores them on disable, focus change and model
// change, like the cleanup preview does.

import type GUI from 'lil-gui';
import type { ViewerApp } from '../app';
import { button, check, note, section, slider, statusLine } from '../tools/ui';
import type { Widget } from '../tools/ui';
import { getOverlay, svgEl } from '../ui/overlay';
import type { Overlay } from '../ui/overlay';
import { CLASH_COLOUR, clearanceColour, computeClearance, DEFAULT_CLEARANCE, legendStops, TIGHT_COLOUR } from './clearance';
import type { Band, ClearanceSettings } from './clearance';

export class ClearanceTool {
  enabled = false;
  readonly settings: ClearanceSettings = { ...DEFAULT_CLEARANCE };
  status = 'Off';
  lastCounts: Record<Band, number> | null = null;
  lastMs = 0;
  private saved = new Map<number, [number, number, number]>();
  private focusSig = '';
  private overlay: Overlay | null = null;
  private layer: SVGGElement | null = null;
  private listeners = new Set<() => void>();
  private folder: GUI | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(readonly app: ViewerApp) {}

  attach(f: GUI): void {
    this.folder = f;
  }

  onChange(cb: () => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }

  private emit(): void {
    for (const l of this.listeners) l();
    this.folder?.controllersRecursive().forEach((c) => c.updateDisplay());
  }

  private ensureOverlay(): void {
    if (this.overlay) return;
    this.overlay = getOverlay(this.app);
    this.layer = this.overlay.layer('clearance');
    this.overlay.onUpdate((ov) => this.drawLegend(ov));
  }

  setEnabled(on: boolean): void {
    this.enabled = on;
    if (on) {
      this.ensureOverlay();
      this.recompute();
    } else {
      this.restore();
      this.lastCounts = null;
      this.status = 'Off';
      this.focusSig = '';
      this.overlay?.invalidate();
    }
    this.emit();
  }

  /** A threshold slider moved: recompute shortly (the sliders fire many times while dragging). */
  settingsChanged(): void {
    if (!this.enabled) return;
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.timer = null;
      this.recompute();
      this.emit();
    }, 120);
    this.overlay?.invalidate();
  }

  private signature(): string {
    const f = this.app.controller?.classification.focus;
    if (!f) return '';
    let h = 0;
    for (const id of f) h = (h * 31 + id) % 1000003;
    return `${this.app.modelName}:${f.size}:${h}`;
  }

  /** Restore the colours we changed. */
  restore(): void {
    if (this.saved.size === 0) return;
    const color = this.app.renderer.state.color;
    for (const [id, c] of this.saved) {
      color[id * 3] = c[0];
      color[id * 3 + 1] = c[1];
      color[id * 3 + 2] = c[2];
    }
    this.saved.clear();
    this.app.renderer.markDirty();
  }

  recompute(): void {
    const app = this.app;
    this.restore();
    this.focusSig = this.signature();
    const loaded = app.loaded;
    const geo = app.geometry;
    if (!loaded || !geo) return;
    const focus = [...app.controller.classification.focus];
    if (focus.length === 0) {
      this.lastCounts = null;
      this.status = 'Select an MEP element (the focus) to see clearances';
      this.overlay?.invalidate();
      return;
    }
    const t0 = performance.now();
    const hides = app.controller.settings.overrides.userHides;
    const ctxClasses = new Set(app.controller.settings.classification.ctxClasses);
    const focusSet = new Set(focus);
    const context: number[] = [];
    for (const e of loaded.model.elements) {
      if (focusSet.has(e.id) || hides.has(e.id) || !ctxClasses.has(e.ifcClass) || !loaded.geometry.hasGeometry(e.id)) continue;
      context.push(e.id);
    }
    const r = computeClearance(focus, context, {
      boundsDistance: (a, b) => geo.boundsDistance(a, b),
      surfaceDistance: (a, b, m) => geo.surfaceDistance(a, b, m),
    }, this.settings);
    const color = app.renderer.state.color;
    for (const [id, d] of r.distances) {
      const c = clearanceColour(d, this.settings);
      if (!c) continue;
      this.saved.set(id, [color[id * 3]!, color[id * 3 + 1]!, color[id * 3 + 2]!]);
      color[id * 3] = c[0];
      color[id * 3 + 1] = c[1];
      color[id * 3 + 2] = c[2];
    }
    app.renderer.markDirty();
    this.lastMs = performance.now() - t0;
    this.lastCounts = r.counts;
    const n = r.counts;
    this.status = `clash ${n.clash}, tight ${n.tight}, ok ${n.ok}, beyond ${n.far} (${context.length} context, ${focus.length} focus, ${r.queried} mesh queries, ${this.lastMs.toFixed(0)} ms)`;
    this.overlay?.invalidate();
  }

  /** Selection or classification changed: refresh when the focus set is different. */
  onStatic(): void {
    if (!this.enabled) return;
    if (this.signature() === this.focusSig) return;
    this.recompute();
    this.emit();
  }

  onModel(): void {
    this.saved.clear(); // the renderer state was replaced
    this.focusSig = '';
    if (this.enabled) this.recompute();
    else this.status = 'Off';
    this.emit();
  }

  // ---------------------------------------------------------------- legend

  private drawLegend(ov: Overlay): void {
    const layer = this.layer;
    if (!layer) return;
    layer.textContent = '';
    if (!this.enabled) return;
    const s = this.settings;
    const w = 210;
    const x = Math.max(8, ov.width - w - 14);
    const y = Math.max(8, ov.height - 124);
    const css = (c: readonly number[]): string => `rgb(${Math.round(c[0]! * 255)},${Math.round(c[1]! * 255)},${Math.round(c[2]! * 255)})`;
    const g = svgEl('g', { 'data-legend': 'clearance' });
    g.appendChild(svgEl('rect', { x, y, width: w, height: 112, rx: 6, fill: 'rgba(14,18,24,0.88)', stroke: '#2d3748' }));
    const text = (tx: number, ty: number, str: string, weight = 400): SVGTextElement => {
      const t = svgEl('text', { x: tx, y: ty, fill: '#dfe6ee', 'font-size': 11.5, 'font-family': 'system-ui,sans-serif', 'font-weight': weight });
      t.textContent = str;
      return t;
    };
    g.appendChild(text(x + 10, y + 18, 'Clearance to focus', 600));
    const rows: Array<[string, string]> = [[css(CLASH_COLOUR), 'clash (touching)'], [css(TIGHT_COLOUR), `tight < ${s.tight.toFixed(2)} m`]];
    rows.forEach(([col, label], i) => {
      g.appendChild(svgEl('rect', { x: x + 10, y: y + 28 + i * 18, width: 14, height: 12, rx: 2, fill: col }));
      g.appendChild(text(x + 32, y + 38 + i * 18, label));
    });
    const defs = svgEl('defs');
    const grad = svgEl('linearGradient', { id: 'xt-clr-grad', x1: 0, x2: 1, y1: 0, y2: 0 });
    for (const [o, c] of legendStops()) grad.appendChild(svgEl('stop', { offset: o, 'stop-color': c }));
    defs.appendChild(grad);
    g.appendChild(defs);
    g.appendChild(svgEl('rect', { x: x + 10, y: y + 64, width: 14, height: 12, rx: 2, fill: 'url(#xt-clr-grad)' }));
    g.appendChild(text(x + 32, y + 74, `ok to ${s.max.toFixed(2)} m`));
    g.appendChild(svgEl('rect', { x: x + 10, y: y + 82, width: 14, height: 12, rx: 2, fill: 'none', stroke: '#6b7686', 'stroke-dasharray': '2 2' }));
    g.appendChild(text(x + 32, y + 92, 'beyond: unchanged'));
    layer.appendChild(g);
  }
}

export function clearancePanel(box: HTMLElement, t: ClearanceTool): () => void {
  const widgets: Widget[] = [];
  const add = (w: Widget): void => {
    widgets.push(w);
    box.appendChild(w.root);
    w.update();
  };
  const status = statusLine(t.status);
  add(check('Show clearance of the context to the focus', () => t.enabled, (v) => t.setEnabled(v)));
  box.appendChild(section('Bands'));
  add(slider('tight (m)', 0.005, 0.5, 0.005, () => t.settings.tight, (v) => {
    t.settings.tight = Math.min(v, t.settings.max);
    t.settingsChanged();
  }, (v) => v.toFixed(3)));
  add(slider('max range (m)', 0.05, 5, 0.05, () => t.settings.max, (v) => {
    t.settings.max = Math.max(v, t.settings.tight);
    t.settingsChanged();
  }, (v) => v.toFixed(2)));
  box.appendChild(button('Recompute', () => { if (t.enabled) { t.recompute(); } else t.setEnabled(true); }, { primary: true, title: 'Recompute for the current focus' }));
  box.appendChild(status);
  box.appendChild(note('Colours the context classes (slabs, walls, beams, ...) by their minimum distance to the focus: red = clash or touching, amber = tight, a blue ramp up to the max range. Beyond the range nothing changes. The focus is the selected element and its connected run.'));
  const refresh = (): void => {
    widgets.forEach((w) => w.update());
    status.set(t.status);
  };
  const off = t.onChange(refresh);
  return off;
}
