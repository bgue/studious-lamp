// Direct-manipulation handles of the section plane on the shared SVG overlay: an arrow along the plane axis (drag to
// push or pull the plane, live offset readout in metres) and 2 rings about the in-plane axes (drag to tilt the plane,
// 15 degree steps, Shift for free). The box keeps its own face handles (plugins/section.ts). The handles take the
// pointer, so a drag never reaches the canvas: no orbit and no pick.

import { Vector3 } from 'three';
import type { ViewerApp } from '../app';
import type { SectionApi } from '../plugins/section';
import { getOverlay, svgEl } from '../ui/overlay';
import type { Overlay } from '../ui/overlay';
import { add, axisDragMetres, cross, normalize, offsetThrough, planeAxes, planeSettingsFor, ringAngle, rotatePlaneAxis, scale, snapAngle, sub, wrapAngle } from './maths';
import type { V2, V3 } from './maths';

const AXIS_COL: Record<string, string> = { x: '#ff6b5e', y: '#58d68d', z: '#5dade2', custom: '#f5b041' };
const RING_COL = ['#f8c471', '#c39bd3'];
const RING_N = 48;
const ARROW_PX = 72;
const RING_PX = 46;

export interface PlaneHandles {
  isDragging(): boolean;
  /** Screen positions (CSS px, stage coordinates) of the handles, for scripts and tests. Null when hidden. */
  positions(): { anchor: V2; tip: V2; rings: V2[]; pxPerMetre: number } | null;
}

type Drag =
  | { kind: 'arrow'; x: number; y: number; offset0: number; axisScreen: V2 }
  | { kind: 'ring'; ring: number; x: number; y: number; n0: V3; k: V3; pivot: V3; centre: V3; flip0: boolean; a0: number | null; tScreen: V2 | null; radius: number };

export function installPlaneHandles(app: ViewerApp, section: SectionApi): PlaneHandles {
  const ov = getOverlay(app);
  const layer = ov.layer('gizmo-plane');
  layer.style.display = 'none';
  const outline = svgEl('polygon', { fill: '#5dade2', 'fill-opacity': 0.07, stroke: '#5dade2', 'stroke-opacity': 0.7, 'stroke-width': 1, 'stroke-dasharray': '6 4' });
  const grab = (e: SVGElement, label: string): void => {
    e.style.pointerEvents = 'all';
    e.style.cursor = 'grab';
    e.style.touchAction = 'none';
    e.setAttribute('aria-label', label);
  };
  const rings = [0, 1].map((i) => {
    const vis = svgEl('polyline', { fill: 'none', stroke: RING_COL[i]!, 'stroke-width': 2, 'stroke-opacity': 0.9 });
    const hit = svgEl('polyline', { fill: 'none', stroke: '#000', 'stroke-opacity': 0, 'stroke-width': 12 });
    hit.style.pointerEvents = 'stroke';
    hit.style.cursor = 'grab';
    hit.style.touchAction = 'none';
    hit.setAttribute('aria-label', 'Drag to tilt the section plane. Steps of 15 degrees, Shift for free.');
    hit.setAttribute('class', `xg-ring xg-ring-${i}`);
    return { vis, hit, world: [] as V3[], screen: [] as V2[] };
  });
  const shaft = svgEl('line', { stroke: '#fff', 'stroke-width': 3, 'stroke-linecap': 'round' });
  const head = svgEl('polygon', { fill: '#fff', stroke: '#141820', 'stroke-width': 1 });
  const arrowHit = svgEl('line', { stroke: '#000', 'stroke-opacity': 0, 'stroke-width': 18, 'stroke-linecap': 'round' });
  arrowHit.setAttribute('class', 'xg-arrow');
  head.setAttribute('class', 'xg-arrow-head');
  grab(arrowHit, 'Drag to move the section plane along its axis');
  grab(head, 'Drag to move the section plane along its axis');
  const dot = svgEl('circle', { r: 4, fill: '#fff', stroke: '#141820', 'stroke-width': 1 });
  const readout = svgEl('text', { 'font-size': 12, 'font-family': 'system-ui, sans-serif', fill: '#ffffff', stroke: '#141820', 'stroke-width': 3, 'paint-order': 'stroke', visibility: 'hidden' });
  readout.setAttribute('class', 'xg-readout');
  layer.append(outline, ...rings.flatMap((r) => [r.vis, r.hit]), shaft, arrowHit, head, dot, readout);

  let drag: Drag | null = null;
  let shown = false;
  let anchorScreen: V2 = [0, 0];
  let tipScreen: V2 = [0, 0];
  let lastPx = 1;

  const camRay = (ev: PointerEvent): { o: V3; d: V3 } => {
    const rect = app.canvas.getBoundingClientRect();
    const x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
    const y = -(((ev.clientY - rect.top) / rect.height) * 2 - 1);
    const cam = app.renderer.camera;
    cam.updateMatrixWorld();
    const p = new Vector3(x, y, 0.5).unproject(cam).sub(cam.position);
    return { o: [cam.position.x, cam.position.y, cam.position.z], d: [p.x, p.y, p.z] };
  };
  const proj = (p: V3): V2 => {
    const s = ov.project(p);
    return [s.x, s.y];
  };
  /** Screen pixels per metre along `dir` at `at` (finite difference of the projection). */
  const screenOf = (at: V3, dir: V3, h: number): V2 => {
    const a = proj(at);
    const b = proj(add(at, scale(dir, h)));
    return [(b[0] - a[0]) / h, (b[1] - a[1]) / h];
  };
  /** Pixels per metre square to the view at `at`. */
  const pxPerMetre = (at: V3): number => {
    const cam = app.renderer.camera;
    const r = new Vector3(1, 0, 0).applyQuaternion(cam.quaternion);
    const dist = Math.max(1e-6, cam.position.distanceTo(new Vector3(...at)));
    const s = screenOf(at, [r.x, r.y, r.z], dist * 0.01);
    return Math.max(1e-6, Math.hypot(s[0], s[1]));
  };

  const active = (): boolean => {
    const c = section.config;
    return c.plane.enabled && c.showHandles && c.plane.axis !== 'camera';
  };
  const anchor = (): V3 => add(section.centre(), scale(section.planeAxis(), section.config.plane.offset));

  const say = (text: string, at: V2): void => {
    readout.textContent = text;
    readout.setAttribute('x', String(at[0] + 14));
    readout.setAttribute('y', String(at[1] - 12));
    readout.setAttribute('visibility', 'visible');
  };

  const start = (ev: PointerEvent, el: SVGElement, d: Drag): void => {
    ev.preventDefault();
    ev.stopPropagation();
    try { el.setPointerCapture(ev.pointerId); } catch { /* synthetic event */ }
    el.style.cursor = 'grabbing';
    drag = d;
  };
  const end = (ev: PointerEvent, el: SVGElement): void => {
    if (!drag) return;
    drag = null;
    el.style.cursor = 'grab';
    readout.setAttribute('visibility', 'hidden');
    try { el.releasePointerCapture(ev.pointerId); } catch { /* already released */ }
    ov.invalidate();
  };

  for (const el of [arrowHit, head] as SVGElement[]) {
    el.addEventListener('pointerdown', (ev) => {
      if (!active()) return;
      const a = anchor();
      const n = section.planeAxis();
      const px = pxPerMetre(a);
      let s = screenOf(a, n, ARROW_PX / px / 4);
      // The axis points (almost) at the viewer: drag up to push along it.
      if (Math.hypot(s[0], s[1]) < 0.2 * px) s = [0, -px];
      start(ev, el, { kind: 'arrow', x: ev.clientX, y: ev.clientY, offset0: section.config.plane.offset, axisScreen: s });
    });
    el.addEventListener('pointermove', (ev) => {
      if (!drag || drag.kind !== 'arrow') return;
      const m = axisDragMetres([ev.clientX - drag.x, ev.clientY - drag.y], drag.axisScreen);
      if (m === null) return;
      const off = Math.min(1000, Math.max(-1000, drag.offset0 + m));
      section.set({ plane: { offset: off } });
      say(`offset ${off >= 0 ? '+' : ''}${off.toFixed(2)} m`, tipScreen);
      ov.invalidate();
    });
    el.addEventListener('pointerup', (ev) => end(ev, el));
    el.addEventListener('pointercancel', (ev) => end(ev, el));
  }

  rings.forEach((ring, i) => {
    const el = ring.hit;
    el.addEventListener('pointerdown', (ev) => {
      if (!active()) return;
      const n0 = section.planeAxis();
      const ax = planeAxes(n0);
      const k = i === 0 ? ax.u : ax.v;
      const pivot = anchor();
      const centre = section.centre();
      const cam = app.renderer.camera;
      const view = normalize(sub(pivot, [cam.position.x, cam.position.y, cam.position.z]));
      const radius = RING_PX / pxPerMetre(pivot);
      let a0: number | null = null;
      let tScreen: V2 | null = null;
      if (Math.abs(view[0] * k[0] + view[1] * k[1] + view[2] * k[2]) > 0.3) {
        const r = camRay(ev);
        a0 = ringAngle(r.o, r.d, pivot, k, n0);
      }
      if (a0 === null) {
        // The ring is seen edge on: drag along the ring's tangent at the grabbed point instead.
        const rect = app.canvas.getBoundingClientRect();
        const mx = ev.clientX - rect.left;
        const my = ev.clientY - rect.top;
        let best = 0;
        let bd = Infinity;
        ring.screen.forEach((p, j) => {
          const d2 = (p[0] - mx) ** 2 + (p[1] - my) ** 2;
          if (d2 < bd) { bd = d2; best = j; }
        });
        const g = ring.world[best] ?? add(pivot, scale(n0, radius));
        const t = normalize(cross(k, sub(g, pivot)));
        tScreen = screenOf(g, t, radius / 8);
      }
      start(ev, el, { kind: 'ring', ring: i, x: ev.clientX, y: ev.clientY, n0, k, pivot, centre, flip0: section.config.plane.flip, a0, tScreen, radius });
    });
    el.addEventListener('pointermove', (ev) => {
      if (!drag || drag.kind !== 'ring' || drag.ring !== i) return;
      let raw: number | null = null;
      if (drag.a0 !== null) {
        const r = camRay(ev);
        const a = ringAngle(r.o, r.d, drag.pivot, drag.k, drag.n0);
        if (a !== null) raw = wrapAngle(a - drag.a0);
      } else if (drag.tScreen) {
        const m = axisDragMetres([ev.clientX - drag.x, ev.clientY - drag.y], drag.tScreen);
        if (m !== null) raw = m / drag.radius;
      }
      if (raw === null) return;
      const ang = snapAngle(raw, 15, ev.shiftKey);
      const n = rotatePlaneAxis(drag.n0, drag.k, ang);
      const s = planeSettingsFor(n, offsetThrough(drag.centre, drag.pivot, n), drag.flip0);
      section.set({ plane: { axis: s.axis, normal: s.normal, offset: s.offset, flip: s.flip } });
      const deg = (ang * 180) / Math.PI;
      say(`tilt ${deg >= 0 ? '+' : ''}${deg.toFixed(ev.shiftKey ? 1 : 0)}°${ev.shiftKey ? '' : ' (Shift: free)'}`, anchorScreen);
      ov.invalidate();
    });
    el.addEventListener('pointerup', (ev) => end(ev, el));
    el.addEventListener('pointercancel', (ev) => end(ev, el));
  });

  const pts = (list: V2[]): string => list.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');

  const update = (o: Overlay): void => {
    shown = active();
    layer.style.display = shown ? '' : 'none';
    if (!shown) return;
    const a = anchor();
    const pa = o.project(a);
    if (!pa.front) {
      layer.style.display = 'none';
      shown = false;
      return;
    }
    const n = section.planeAxis();
    const px = pxPerMetre(a);
    lastPx = px;
    const L = ARROW_PX / px;
    const R = RING_PX / px;
    const col = AXIS_COL[section.config.plane.axis] ?? '#ffffff';
    anchorScreen = [pa.x, pa.y];
    // Plane outline: a square about the anchor, as wide as the box (or the model).
    const ax = planeAxes(n);
    const box = section.config.box;
    let half = R * 1.8;
    if (box.min && box.max) half = Math.max(half, 0.5 * Math.hypot(box.max[0] - box.min[0], box.max[1] - box.min[1], box.max[2] - box.min[2]) / Math.SQRT2);
    else {
      const b = app.loaded?.geometry.totalBounds();
      if (b && !b.isEmpty()) half = Math.max(half, 0.5 * b.min.distanceTo(b.max) / Math.SQRT2);
    }
    const corners = [[-1, -1], [1, -1], [1, 1], [-1, 1]].map(([i, j]) => o.project(add(a, add(scale(ax.u, i! * half), scale(ax.v, j! * half)))));
    if (corners.every((c) => c.front)) {
      outline.setAttribute('visibility', 'visible');
      outline.setAttribute('points', pts(corners.map((c) => [c.x, c.y])));
      outline.setAttribute('stroke', col);
      outline.setAttribute('fill', col);
    } else outline.setAttribute('visibility', 'hidden');
    // Arrow along the axis.
    const tip = o.project(add(a, scale(n, L)));
    const tail = o.project(add(a, scale(n, -L * 0.35)));
    tipScreen = [tip.x, tip.y];
    for (const l of [shaft, arrowHit]) {
      l.setAttribute('x1', String(tail.x));
      l.setAttribute('y1', String(tail.y));
      l.setAttribute('x2', String(tip.x));
      l.setAttribute('y2', String(tip.y));
    }
    shaft.setAttribute('stroke', col);
    let dx = tip.x - pa.x;
    let dy = tip.y - pa.y;
    const dl = Math.hypot(dx, dy);
    if (dl < 1e-3) { dx = 0; dy = -1; } else { dx /= dl; dy /= dl; }
    const hw = 7;
    const hl = 14;
    head.setAttribute('points', pts([[tip.x + dx * hl, tip.y + dy * hl], [tip.x - dy * hw, tip.y + dx * hw], [tip.x + dy * hw, tip.y - dx * hw]]));
    head.setAttribute('fill', col);
    dot.setAttribute('cx', String(pa.x));
    dot.setAttribute('cy', String(pa.y));
    // Rings about the 2 in-plane axes.
    rings.forEach((ring, i) => {
      const k = i === 0 ? ax.u : ax.v;
      const e1 = n;
      const e2 = cross(k, n);
      ring.world = [];
      ring.screen = [];
      let ok = true;
      for (let j = 0; j <= RING_N; j++) {
        const t = (j / RING_N) * Math.PI * 2;
        const w = add(a, add(scale(e1, Math.cos(t) * R), scale(e2, Math.sin(t) * R)));
        const s = o.project(w);
        if (!s.front) ok = false;
        ring.world.push(w);
        ring.screen.push([s.x, s.y]);
      }
      const p = pts(ring.screen);
      ring.vis.setAttribute('points', p);
      ring.hit.setAttribute('points', p);
      ring.vis.setAttribute('visibility', ok ? 'visible' : 'hidden');
      ring.hit.setAttribute('visibility', ok ? 'visible' : 'hidden');
    });
    if (drag?.kind === 'arrow') {
      readout.setAttribute('x', String(tip.x + 14));
      readout.setAttribute('y', String(tip.y - 12));
    }
  };
  ov.onUpdate(update);
  section.onChange(() => ov.invalidate());

  return {
    isDragging: () => drag !== null,
    positions: () => (shown ? { anchor: anchorScreen, tip: tipScreen, rings: rings.map((r): V2 => r.screen[Math.round(RING_N / 8)] ?? [0, 0]), pxPerMetre: lastPx } : null),
  };
}
