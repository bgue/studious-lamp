// Live viewer markup on the shared SVG overlay: numbered topic pins (faded behind geometry, edge markers when off screen)
// and the annotations of the applied viewpoint (callouts, notes, arrows, linked measurements). Also the click-to-place
// mode for pins and annotations (Escape cancels) and dragging of annotation text boxes.
// Layout comes from annotate.ts, the same code that burns the markup into exported snapshots.

import { Matrix4 } from 'three';
import { getOverlay, svgEl } from '../ui/overlay';
import type { Overlay } from '../ui/overlay';
import { currentMeasurements } from '../measure/current';
import type { Measurement } from '../measure/maths';
import { MARKUP_FONT, layoutAnnotation, layoutPin, projectPoint } from './annotate';
import type { DrawOp, LayoutContext } from './annotate';
import type { BcfController } from './controller';
import type { BcfAnnotationType } from './model';

export type PlaceKind = 'pin' | BcfAnnotationType;
const CLICK_SLOP = 5;

export class BcfMarkupView {
  private overlay: Overlay | null = null;
  private layer: SVGGElement | null = null;
  private readonly vp = new Matrix4();
  /** Placement in progress: the next click on the model places it. */
  placing: { kind: PlaceKind; topic: string; text: string } | null = null;
  /** Highlighted annotation (list click, box drag). */
  selected: string | null = null;
  /** The drawer can take over text editing on a double click of a box. */
  onEdit: ((guid: string) => boolean) | null = null;
  private down: { x: number; y: number } | null = null;
  private drag: { guid: string; startX: number; startY: number; off: [number, number]; moved: boolean } | null = null;
  private escHandler: ((e: KeyboardEvent) => void) | null = null;
  get dragging(): boolean {
    return this.drag !== null;
  }
  private readonly listeners = new Set<() => void>();

  constructor(readonly c: BcfController) {
    const canvas = c.app.canvas;
    // Capture phase on the canvas: runs before the viewer's click-to-select (same pattern as the measure tool).
    canvas.addEventListener('pointerdown', (e) => {
      this.down = this.placing && e.button === 0 ? { x: e.clientX, y: e.clientY } : null;
    }, true);
    canvas.addEventListener('pointerup', (e) => this.onPointerUp(e), true);
    c.onChange(() => this.overlay?.invalidate());
    c.markup = this;
  }

  onChange(cb: () => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }
  private emit(): void {
    this.overlay?.invalidate();
    for (const l of this.listeners) l();
  }

  /** Create the overlay layer once a model is loaded (called per frame by the plugin). */
  tick(): void {
    if (this.overlay || !this.c.app.loaded) return;
    this.overlay = getOverlay(this.c.app);
    this.layer = this.overlay.layer('bcf-markup');
    this.overlay.onUpdate((ov) => this.draw(ov));
  }

  invalidate(): void {
    this.overlay?.invalidate();
  }

  // ---------------------------------------------------------------- placement

  /** Start click-to-place for a pin or an annotation on `topic`. Returns false when there is no model. */
  start(kind: PlaceKind, topic: string, text = ''): boolean {
    if (!this.c.app.loaded) return false;
    this.placing = { kind, topic, text };
    this.c.app.canvas.style.cursor = 'crosshair';
    this.addEsc();
    const what = kind === 'pin' ? 'the pin' : kind === 'note' ? 'the note' : `the ${kind} target element`;
    this.c.setStatus(`Click the model to place ${what} (Esc cancels)`);
    this.emit();
    return true;
  }

  cancel(quiet = false): void {
    if (!this.placing) return;
    this.placing = null;
    this.c.app.canvas.style.cursor = '';
    this.removeEsc();
    if (!quiet) this.c.setStatus('Placement cancelled');
    this.emit();
  }

  private addEsc(): void {
    if (this.escHandler) return;
    // Window capture runs before the tool drawer's own Escape handler: the first Escape cancels the placement only.
    this.escHandler = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || !this.placing) return;
      e.stopImmediatePropagation();
      e.preventDefault();
      this.cancel();
    };
    window.addEventListener('keydown', this.escHandler, true);
  }
  private removeEsc(): void {
    if (!this.escHandler) return;
    window.removeEventListener('keydown', this.escHandler, true);
    this.escHandler = null;
  }

  private onPointerUp(e: PointerEvent): void {
    if (!this.placing || e.button !== 0 || !this.down) return;
    const moved = Math.hypot(e.clientX - this.down.x, e.clientY - this.down.y);
    this.down = null;
    if (moved > CLICK_SLOP) return; // an orbit drag
    // Hide the click from the viewer's select handler (it ignores other buttons); stopping it would starve OrbitControls.
    try {
      Object.defineProperty(e, 'button', { value: 2 });
    } catch {
      /* the event stays as is */
    }
    this.placeAtClient(e.clientX, e.clientY);
  }

  /** Place at a client position (also used by scripts). Returns true when something was placed. */
  placeAtClient(clientX: number, clientY: number): boolean {
    const p = this.placing;
    if (!p) return false;
    const r = this.c.app.canvas.getBoundingClientRect();
    const hit = this.c.pick(((clientX - r.left) / r.width) * 2 - 1, -(((clientY - r.top) / r.height) * 2 - 1));
    if (!hit) {
      this.c.setStatus('No surface under the cursor; click the model (Esc cancels)');
      return false;
    }
    const gid = this.c.app.controller.model.elements[hit.element]?.globalId;
    this.cancel(true);
    try {
      if (p.kind === 'pin') this.c.setPin(p.topic, hit.point, gid);
      else {
        const a = this.c.addAnnotation(p.topic, {
          type: p.kind,
          text: p.text,
          anchor: p.kind === 'note' ? { kind: 'point', point: hit.point } : { kind: 'element', point: hit.point, elementGuid: gid },
        });
        this.selected = a.guid;
      }
    } catch (err) {
      this.c.setStatus(err instanceof Error ? err.message : String(err));
      return false;
    }
    this.emit();
    return true;
  }

  /** Link a measurement of the measure tool to the active viewpoint of a topic as a callout. */
  linkMeasurement(topic: string, m: Measurement, text?: string): void {
    const a = this.c.addAnnotation(topic, { type: 'callout', text, anchor: { kind: 'measurement', measurement: m } });
    this.selected = a.guid;
    this.emit();
  }

  measurements(): readonly Measurement[] {
    return currentMeasurements();
  }

  // ---------------------------------------------------------------- drawing

  private context(ov: Overlay): LayoutContext {
    const cam = this.c.app.renderer.camera;
    cam.updateMatrixWorld();
    this.vp.multiplyMatrices(cam.projectionMatrix, cam.matrixWorldInverse);
    const m = this.vp.elements;
    const w = ov.width;
    const h = ov.height;
    return { width: w, height: h, shift: this.c.shift, scale: 1, project: (p) => projectPoint(m, w, h, p), occluded: (p) => this.c.occluded(p) };
  }

  private draw(ov: Overlay): void {
    const layer = this.layer;
    if (!layer) return;
    layer.textContent = '';
    if (!this.c.app.loaded) return;
    const ctx = this.context(ov);
    const vis = this.c.visibleAnnotations();
    if (vis) {
      for (const a of vis.list) {
        const g = svgEl('g', { 'data-bcf-ann': a.guid });
        renderOps(g, layoutAnnotation(a, ctx, { selected: a.guid === this.selected }));
        layer.appendChild(g);
      }
    }
    for (const t of this.c.pinnedTopics()) {
      const g = svgEl('g', { 'data-bcf-pin': t.guid });
      renderOps(g, layoutPin(t.pin!, String(this.c.pinNumber(t)), ctx, { active: t.guid === this.c.selectedTopic, key: `pin:${t.guid}` }));
      const title = svgEl('title');
      title.textContent = `${this.c.pinNumber(t)}. ${t.title}`;
      g.appendChild(title);
      layer.appendChild(g);
    }
    this.wire(layer);
  }

  /** Pointer handlers on the interactive parts (the overlay itself ignores the pointer). */
  private wire(layer: SVGGElement): void {
    for (const el of Array.from(layer.querySelectorAll<SVGElement>('[data-role="pin"], [data-role="edge"]'))) {
      el.style.pointerEvents = 'all';
      el.style.cursor = 'pointer';
      el.addEventListener('pointerdown', (e: PointerEvent) => e.stopPropagation());
      el.addEventListener('click', (e: MouseEvent) => {
        e.stopPropagation();
        const guid = el.getAttribute('data-key')!.slice(4);
        this.activateTopic(guid);
      });
    }
    for (const el of Array.from(layer.querySelectorAll<SVGElement>('[data-role="box"]'))) {
      el.style.pointerEvents = 'all';
      el.style.cursor = 'move';
      const guid = el.getAttribute('data-key')!;
      el.addEventListener('pointerdown', (e: PointerEvent) => this.startDrag(e, guid));
      el.addEventListener('dblclick', (e: MouseEvent) => {
        e.stopPropagation();
        this.edit(guid);
      });
    }
  }

  /** Select a topic and apply its first viewpoint (pin click). */
  activateTopic(guid: string): void {
    const t = this.c.topic(guid);
    if (!t) return;
    this.c.select(guid);
    if (t.viewpoints.some((v) => v.data)) this.c.applyViewpoint(guid);
    this.emit();
  }

  private edit(guid: string): void {
    if (this.onEdit?.(guid)) return;
    const f = this.c.findAnnotation(guid);
    if (!f) return;
    const v = window.prompt('Annotation text', f.ann.text);
    if (v !== null) this.c.updateAnnotation(guid, { text: v });
  }

  private startDrag(e: PointerEvent, guid: string): void {
    if (e.button !== 0) return;
    const f = this.c.findAnnotation(guid);
    if (!f) return;
    e.stopPropagation();
    e.preventDefault();
    this.selected = guid;
    this.drag = { guid, startX: e.clientX, startY: e.clientY, off: [...f.ann.offset], moved: false };
    const h = Math.max(1, this.overlay?.height ?? 1);
    const move = (ev: PointerEvent): void => {
      const d = this.drag;
      if (!d) return;
      const dx = ev.clientX - d.startX;
      const dy = ev.clientY - d.startY;
      if (!d.moved && Math.hypot(dx, dy) < 2) return;
      d.moved = true;
      this.c.updateAnnotation(d.guid, { offset: [d.off[0] + dx / h, d.off[1] + dy / h] }, true);
    };
    const up = (): void => {
      window.removeEventListener('pointermove', move, true);
      window.removeEventListener('pointerup', up, true);
      const d = this.drag;
      this.drag = null;
      if (d?.moved) {
        const a = this.c.findAnnotation(d.guid)?.ann;
        if (a) this.c.updateAnnotation(d.guid, { offset: a.offset });
      }
      this.emit();
    };
    window.addEventListener('pointermove', move, true);
    window.addEventListener('pointerup', up, true);
    this.emit();
  }

  /** Highlight an annotation and apply its viewpoint when another one is active (list click). */
  focus(guid: string): void {
    const f = this.c.findAnnotation(guid);
    if (!f) return;
    this.selected = guid;
    if (this.c.applied?.viewpoint !== f.ref.guid) this.c.applyViewpoint(f.topic.guid, f.ref.guid);
    this.emit();
  }
}

/** Draw operations as SVG elements (the same operations drawOps paints on a canvas). */
export function renderOps(g: SVGGElement, ops: readonly DrawOp[]): void {
  for (const o of ops) {
    let e: SVGElement;
    switch (o.op) {
      case 'line':
        e = svgEl('line', { x1: o.x1, y1: o.y1, x2: o.x2, y2: o.y2, stroke: o.stroke, 'stroke-width': o.width, 'stroke-linecap': 'round' });
        if (o.dash) e.setAttribute('stroke-dasharray', o.dash.join(' '));
        break;
      case 'poly':
        e = svgEl('polygon', { points: o.points.join(' '), fill: o.fill, 'stroke-linejoin': 'round' });
        if (o.stroke && o.width) { e.setAttribute('stroke', o.stroke); e.setAttribute('stroke-width', String(o.width)); }
        break;
      case 'circle':
        e = svgEl('circle', { cx: o.x, cy: o.y, r: o.r, fill: o.fill });
        if (o.stroke && o.width) { e.setAttribute('stroke', o.stroke); e.setAttribute('stroke-width', String(o.width)); }
        if (o.dash) e.setAttribute('stroke-dasharray', o.dash.join(' '));
        break;
      case 'rect':
        e = svgEl('rect', { x: o.x, y: o.y, width: o.w, height: o.h, rx: o.r, fill: o.fill });
        if (o.stroke && o.width) { e.setAttribute('stroke', o.stroke); e.setAttribute('stroke-width', String(o.width)); }
        break;
      case 'text':
        e = svgEl('text', { x: o.x, y: o.y, fill: o.fill, 'font-size': o.size, 'font-family': MARKUP_FONT, 'text-anchor': o.align });
        if (o.bold) e.setAttribute('font-weight', '700');
        e.style.whiteSpace = 'pre';
        e.style.userSelect = 'none';
        e.textContent = o.text;
        break;
    }
    if (o.alpha !== undefined && o.alpha !== 1) e.setAttribute('opacity', String(o.alpha));
    if (o.key) e.setAttribute('data-key', o.key);
    if (o.role) e.setAttribute('data-role', o.role);
    g.appendChild(e);
  }
}
