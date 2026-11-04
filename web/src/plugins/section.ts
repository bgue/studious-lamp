// Section plugin: a section box (fitted to the selection or the model, six draggable face handles) and a section
// plane, both feeding renderer.setClipPlanes (see docs-features/section.md). This file owns the settings, the lil-gui
// folder, the drawer, the handles on the shared SVG overlay, the actions and the params section.

import { Vector3 } from 'three';
import type { AppPlugin, ViewerApp } from '../app';
import { registerAction } from '../input/actions';
import { cloneSection, defaultSection, mergeSection, PLANE_AXES } from '../section/config';
import type { SectionConfig } from '../section/config';
import { BOX_EDGES, boxCentre, boxCorners, boxHandles, closestParamOnLine, dragHandle, fitBox, planesEqual, planesFor, sectionPlane } from '../section/maths';
import type { Box6, ClipPlane, Handle, SectionBox, Vec3 } from '../section/maths';
import { registerTool } from '../tools/registry';
import { button, check, note, row, section, select, slider, statusLine } from '../tools/ui';
import type { Widget } from '../tools/ui';
import { el } from '../ui/dom';
import { getOverlay, svgEl } from '../ui/overlay';
import type { Overlay } from '../ui/overlay';
import { registerParamSection } from '../ui/params';

export interface SectionApi {
  config: SectionConfig;
  /** Merge any subset of the settings (box, plane, caps, capColor, showHandles); returns the dotted names it could not use. */
  set(partial: unknown): string[];
  /** Fit the box to the selection (else the focus, else the model), enable it, and return it. */
  fitToSelection(): SectionBox | null;
  fitToModel(): SectionBox | null;
  /** Switch box and plane off and remove every clip plane. */
  clear(): void;
  /** The planes this plugin would send to the renderer right now. */
  planes(): ClipPlane[];
  /** The point the plane offset is measured from: the box centre, else the model centre. */
  centre(): Vec3;
  /** Unit axis direction of the plane before the flip (offset grows along it); the view direction for axis `camera`. */
  planeAxis(): Vec3;
  /** Call `cb` after every settings change (drawer, panel, gizmo, handle drag). Returns an unsubscribe function. */
  onChange(cb: () => void): () => void;
}

declare global {
  interface Window {
    __xraySection?: SectionApi;
  }
}

const config = defaultSection();
let appRef: ViewerApp | null = null;
let folderRoot: { controllersRecursive(): Array<{ updateDisplay(): unknown }> } | null = null;
let offsetCtl: { min(v: number): unknown; max(v: number): unknown } | null = null;
/** The renderer's clipVersion after our last push; a different value means someone else (BCF) set planes. */
let ownedVersion = -1;
let foreign = false;
let pushedAny = false;
let lastPlanes: ClipPlane[] = [];
let lastCap = '';
const fwd = new Vector3();
const listeners = new Set<() => void>();

function refreshGui(): void {
  folderRoot?.controllersRecursive().forEach((c) => c.updateDisplay());
  for (const l of listeners) l();
}

/** Any change of the section settings takes the planes back from a foreign owner. */
function touch(): void {
  foreign = false;
  overlayInvalidate?.();
}
let overlayInvalidate: (() => void) | null = null;

// ---------------------------------------------------------------- fitting

function elementBoxes(app: ViewerApp, ids: Iterable<number>): Box6[] {
  const els = app.loaded?.model.elements;
  if (!els) return [];
  const out: Box6[] = [];
  for (const id of ids) {
    const b = els[id]?.bounds as Box6 | undefined;
    if (b) out.push(b);
  }
  return out;
}

function modelBoxes(app: ViewerApp): Box6[] {
  const b = app.loaded?.geometry.totalBounds();
  return b && !b.isEmpty() ? [[b.min.x, b.min.y, b.min.z, b.max.x, b.max.y, b.max.z]] : [];
}

function fit(app: ViewerApp, mode: 'selection' | 'model'): SectionBox | null {
  let boxes: Box6[] = [];
  if (mode === 'selection') {
    boxes = elementBoxes(app, app.controller?.selection ?? []);
    if (boxes.length === 0 && app.controller) boxes = elementBoxes(app, app.controller.classification.focus);
  }
  if (boxes.length === 0) boxes = modelBoxes(app);
  const b = fitBox(boxes, config.box.margin);
  if (!b) return null;
  config.box.min = b.min;
  config.box.max = b.max;
  config.box.fit = mode;
  return b;
}

function currentBox(): SectionBox | null {
  const { min, max } = config.box;
  return min && max ? { min, max } : null;
}

function centre(app: ViewerApp): Vec3 {
  const b = currentBox();
  if (b) return boxCentre(b);
  const m = modelBoxes(app)[0];
  return m ? [(m[0] + m[3]) / 2, (m[1] + m[4]) / 2, (m[2] + m[5]) / 2] : [0, 0, 0];
}

function computePlanes(app: ViewerApp): ClipPlane[] {
  let plane: ClipPlane | null = null;
  if (config.plane.enabled) {
    app.renderer.camera.getWorldDirection(fwd);
    plane = sectionPlane(config.plane.axis, centre(app), config.plane.offset, config.plane.flip, [fwd.x, fwd.y, fwd.z], config.plane.normal);
  }
  return planesFor(currentBox(), config.box.enabled, plane);
}

function doFit(mode: 'selection' | 'model'): SectionBox | null {
  const app = appRef;
  if (!app?.loaded) return null;
  const b = fit(app, mode);
  if (b) config.box.enabled = true;
  touch();
  refreshGui();
  return b;
}

function clearAll(): void {
  config.box.enabled = false;
  config.plane.enabled = false;
  config.plane.offset = 0;
  config.plane.flip = false;
  config.box.min = config.box.max = null;
  const r = appRef?.renderer;
  if (r) {
    r.setClipPlanes(null);
    ownedVersion = r.clipVersion;
  }
  pushedAny = false;
  lastPlanes = [];
  foreign = false;
  refreshGui();
  overlayInvalidate?.();
}

const api: SectionApi = {
  config,
  set(partial) {
    const res = mergeSection(config, partial);
    if (appRef?.loaded) {
      if (res.refit) fit(appRef, config.box.fit);
      else if (config.box.enabled && !currentBox()) fit(appRef, config.box.fit);
    }
    touch();
    refreshGui();
    return res.bad;
  },
  fitToSelection: () => doFit('selection'),
  fitToModel: () => doFit('model'),
  clear: clearAll,
  planes: () => (appRef ? computePlanes(appRef) : []),
  centre: () => (appRef ? centre(appRef) : [0, 0, 0]),
  planeAxis() {
    if (appRef) appRef.renderer.camera.getWorldDirection(fwd);
    return sectionPlane(config.plane.axis, [0, 0, 0], 0, false, [fwd.x, fwd.y, fwd.z], config.plane.normal).normal;
  },
  onChange(cb) {
    listeners.add(cb);
    return () => listeners.delete(cb);
  },
};

// ---------------------------------------------------------------- per frame

function pushPlanes(app: ViewerApp): void {
  const r = app.renderer;
  if (r.clipVersion !== ownedVersion && pushedAny) foreign = true; // someone else (a BCF viewpoint) took the planes
  if (foreign) return;
  const want = config.box.enabled || config.plane.enabled;
  if (!want && !pushedAny) return;
  if (want && config.box.enabled && !currentBox() && app.loaded) fit(app, config.box.fit);
  const planes = want ? computePlanes(app) : [];
  const cap = `${config.caps}:${config.capColor.join(',')}`;
  if (planesEqual(planes, lastPlanes, 1e-7) && cap === lastCap && (planes.length > 0) === pushedAny) return;
  r.setClipPlanes(planes.length ? planes : null, { cap: config.caps, capColor: config.capColor });
  ownedVersion = r.clipVersion;
  lastPlanes = planes;
  lastCap = cap;
  pushedAny = planes.length > 0;
}

// ---------------------------------------------------------------- handles on the overlay

const AXIS_COL = ['#ff6b5e', '#58d68d', '#5dade2'];

function installHandles(app: ViewerApp): void {
  const ov = getOverlay(app);
  const layer = ov.layer('section');
  const lines = BOX_EDGES.map(() => svgEl('line', { stroke: '#f5b041', 'stroke-width': 1, 'stroke-opacity': 0.55, 'stroke-dasharray': '4 3' }));
  const dots = [0, 1, 2, 3, 4, 5].map((i) => {
    const c = svgEl('circle', { r: 7, fill: AXIS_COL[i >> 1]!, 'fill-opacity': 0.85, stroke: '#ffffff', 'stroke-width': 1.5 });
    c.style.pointerEvents = 'all';
    c.style.cursor = 'grab';
    c.style.touchAction = 'none';
    return c;
  });
  for (const l of lines) layer.appendChild(l);
  for (const d of dots) layer.appendChild(d);
  // Live readout while a face is dragged: the face coordinate and the box size along that axis, in metres.
  const readout = svgEl('text', { 'font-size': 12, 'font-family': 'system-ui, sans-serif', fill: '#ffffff', stroke: '#141820', 'stroke-width': 3, 'paint-order': 'stroke', visibility: 'hidden' });
  readout.setAttribute('class', 'xs-readout');
  layer.appendChild(readout);
  layer.style.display = 'none';

  let drag: { index: number; box: SectionBox; handle: Handle; grabT: number } | null = null;

  const ray = (ev: PointerEvent): { o: Vec3; d: Vec3 } => {
    const rect = app.canvas.getBoundingClientRect();
    const x = ((ev.clientX - rect.left) / rect.width) * 2 - 1;
    const y = -(((ev.clientY - rect.top) / rect.height) * 2 - 1);
    const cam = app.renderer.camera;
    cam.updateMatrixWorld();
    const p = new Vector3(x, y, 0.5).unproject(cam).sub(cam.position);
    return { o: [cam.position.x, cam.position.y, cam.position.z], d: [p.x, p.y, p.z] };
  };

  dots.forEach((dot, i) => {
    dot.addEventListener('pointerdown', (ev) => {
      const b = currentBox();
      if (!b) return;
      ev.preventDefault();
      ev.stopPropagation();
      dot.setPointerCapture(ev.pointerId);
      const handle = boxHandles(b)[i]!;
      const rr = ray(ev);
      drag = { index: i, box: b, handle, grabT: closestParamOnLine(rr.o, rr.d, handle.point, handle.dir) ?? 0 };
      dot.style.cursor = 'grabbing';
    });
    dot.addEventListener('pointermove', (ev) => {
      if (!drag || drag.index !== i) return;
      const rr = ray(ev);
      const nb = dragHandle(drag.box, drag.handle, rr.o, rr.d, drag.grabT);
      if (!nb) return;
      config.box.min = nb.min;
      config.box.max = nb.max;
      config.box.enabled = true;
      const a = drag.handle.axis;
      const at = drag.handle.side === 'min' ? nb.min[a] : nb.max[a];
      readout.textContent = `${'xyz'[a]} ${at.toFixed(2)} m, size ${(nb.max[a] - nb.min[a]).toFixed(2)} m`;
      touch();
      refreshGui();
      ov.invalidate();
    });
    const end = (ev: PointerEvent): void => {
      if (drag && drag.index === i) {
        drag = null;
        readout.setAttribute('visibility', 'hidden');
        dot.style.cursor = 'grab';
        try { dot.releasePointerCapture(ev.pointerId); } catch { /* already released */ }
      }
    };
    dot.addEventListener('pointerup', end);
    dot.addEventListener('pointercancel', end);
  });

  const update = (o: Overlay): void => {
    const b = currentBox();
    const show = config.box.enabled && config.showHandles && b !== null;
    layer.style.display = show ? '' : 'none';
    if (!show || !b) return;
    const corners = boxCorners(b).map((c) => o.project(c));
    BOX_EDGES.forEach(([a, c], k) => {
      const pa = corners[a]!;
      const pc = corners[c]!;
      const l = lines[k]!;
      if (!pa.front || !pc.front) {
        l.setAttribute('visibility', 'hidden');
        return;
      }
      l.setAttribute('visibility', 'visible');
      l.setAttribute('x1', String(pa.x));
      l.setAttribute('y1', String(pa.y));
      l.setAttribute('x2', String(pc.x));
      l.setAttribute('y2', String(pc.y));
    });
    const hs = boxHandles(b);
    dots.forEach((d, i) => {
      const p = o.project(hs[i]!.point);
      d.setAttribute('visibility', p.front ? 'visible' : 'hidden');
      d.setAttribute('cx', String(p.x));
      d.setAttribute('cy', String(p.y));
      if (drag && drag.index === i) {
        readout.setAttribute('x', String(p.x + 12));
        readout.setAttribute('y', String(p.y - 10));
        readout.setAttribute('visibility', p.front ? 'visible' : 'hidden');
      }
    });
  };
  ov.onUpdate(update);
  overlayInvalidate = () => ov.invalidate();
}

// ---------------------------------------------------------------- drawer

const ICON =
  '<svg viewBox="0 0 20 20" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M4 6.5 10 3l6 3.5v7L10 17l-6-3.5z" stroke-dasharray="2 2"/><path d="M2.5 11.5 10 8l7.5 3.5"/></svg>';

const toHex = (c: readonly number[]): string => '#' + c.map((x) => Math.round(Math.min(1, Math.max(0, x)) * 255).toString(16).padStart(2, '0')).join('');
const fromHex = (h: string): [number, number, number] => [parseInt(h.slice(1, 3), 16) / 255, parseInt(h.slice(3, 5), 16) / 255, parseInt(h.slice(5, 7), 16) / 255];

function drawer(box: HTMLElement): (() => void) | void {
  const widgets: Widget[] = [];
  const add = (w: Widget, into: HTMLElement = box): void => {
    widgets.push(w);
    into.appendChild(w.root);
    w.update();
  };
  const f2 = (v: number): string => v.toFixed(2);
  box.appendChild(section('Section box'));
  add(check('box (C)', () => config.box.enabled, (v) => api.set({ box: { enabled: v } })));
  box.appendChild(row(
    button('Fit to selection', () => void api.fitToSelection(), { primary: true, title: 'Fit the box to the selection plus the margin (Shift+C)' }),
    button('Fit to model', () => void api.fitToModel(), { title: 'Fit the box to the whole model plus the margin' }),
  ));
  add(slider('margin (m)', 0, 5, 0.05, () => config.box.margin, (v) => api.set({ box: { margin: v } }), f2));
  // Numeric min / max (they follow the handles).
  const names = ['x', 'y', 'z'];
  for (const which of ['min', 'max'] as const) {
    const r = el('div', 'xt-row');
    for (let a = 0; a < 3; a++) {
      const lab = el('label', 'xt-select');
      const inp = el('input', 'xt-num', { type: 'number', step: '0.05' });
      inp.style.width = '70px';
      lab.append(el('span', 'xt-lbl', undefined, `${which} ${names[a]}`), inp);
      inp.addEventListener('change', () => {
        const v = Number(inp.value);
        const cur = config.box[which];
        if (!Number.isFinite(v) || !cur) return;
        const next: Vec3 = [cur[0], cur[1], cur[2]];
        next[a] = v;
        api.set({ box: { [which]: next, enabled: true } });
      });
      widgets.push({ root: lab, update: () => { const c = config.box[which]; if (c && document.activeElement !== inp) inp.value = c[a]!.toFixed(2); } });
      r.appendChild(lab);
    }
    box.appendChild(r);
  }
  add(check('show handles', () => config.showHandles, (v) => api.set({ showHandles: v })));
  box.appendChild(section('Section plane'));
  add(check('plane (Alt+C)', () => config.plane.enabled, (v) => api.set({ plane: { enabled: v } })));
  add(select('axis', PLANE_AXES, () => config.plane.axis, (v) => api.set({ plane: { axis: v } })));
  add(slider('offset (m)', -50, 50, 0.05, () => config.plane.offset, (v) => api.set({ plane: { offset: v } }), f2));
  add(check('flip', () => config.plane.flip, (v) => api.set({ plane: { flip: v } })));
  box.appendChild(section('Caps'));
  add(check('caps', () => config.caps, (v) => api.set({ caps: v })));
  const colorRow = el('label', 'xt-select');
  const color = el('input', undefined, { type: 'color' });
  colorRow.append(el('span', 'xt-lbl', undefined, 'cap colour'), color);
  color.addEventListener('input', () => api.set({ capColor: fromHex(color.value) }));
  widgets.push({ root: colorRow, update: () => { color.value = toHex(config.capColor); } });
  box.appendChild(colorRow);
  box.appendChild(row(button('Clear section', () => api.clear(), { title: 'Remove the box and the plane' })));
  const st = statusLine('');
  box.appendChild(st);
  box.appendChild(note('Drag the round handles on the box faces to resize it. C toggles the box, Shift+C fits it to the selection, Alt+C toggles the plane.'));
  const upd = (): void => {
    widgets.forEach((w) => w.update());
    const n = appRef?.renderer.getClipPlanes()?.length ?? 0;
    st.set(n ? `${n} clip plane${n === 1 ? '' : 's'} active` : 'No section');
  };
  listeners.add(upd);
  const t = setInterval(upd, 500);
  upd();
  return () => {
    clearInterval(t);
    listeners.delete(upd);
  };
}

// ---------------------------------------------------------------- plugin

export const sectionPlugin: AppPlugin = {
  name: 'section',

  install(app: ViewerApp): void {
    appRef = app;
    window.__xraySection = api;

    registerAction({
      id: 'section.toggleBox',
      label: 'Section box: toggle',
      group: 'Modes',
      keys: ['c'],
      run: () => {
        if (config.box.enabled) api.set({ box: { enabled: false } });
        else if (!currentBox()) doFit(config.box.fit);
        else api.set({ box: { enabled: true } });
      },
    });
    registerAction({ id: 'section.fitSelection', label: 'Section box: fit to selection', group: 'Modes', keys: ['Shift+c'], run: () => void doFit('selection') });
    registerAction({ id: 'section.togglePlane', label: 'Section plane: toggle', group: 'Modes', keys: ['Alt+c'], run: () => api.set({ plane: { enabled: !config.plane.enabled } }) });
    registerAction({ id: 'section.clear', label: 'Section: clear', group: 'Modes', keys: [], run: () => api.clear() });

    registerTool({
      id: 'section',
      label: 'Section',
      title: 'Section box and plane with capped cuts (C)',
      icon: ICON,
      order: 46,
      drawerWidth: 340,
      panel: (box) => drawer(box),
      isActive: () => config.box.enabled || config.plane.enabled,
    });

    registerParamSection('section', {
      share: true,
      collect: () => cloneSection(config),
      apply(value, bad, path) {
        if (value === null || typeof value !== 'object') {
          bad.push(path);
          return;
        }
        const res = mergeSection(config, value, path);
        bad.push(...res.bad);
        if (res.refit && appRef?.loaded) fit(appRef, config.box.fit);
        touch();
        refreshGui();
      },
    });

    installHandles(app);

    const gui = app.panel;
    if (!gui) return;
    const root = gui.addFolder('Section');
    folderRoot = root;
    root.close();
    root.add(config.box, 'enabled').name('box');
    root.add({ fitSelection: () => void doFit('selection') }, 'fitSelection').name('Fit box to selection');
    root.add({ fitModel: () => void doFit('model') }, 'fitModel').name('Fit box to model');
    root.add(config.box, 'margin', 0, 5, 0.05).name('margin (m)').onFinishChange(() => {
      if (appRef?.loaded && currentBox()) fit(appRef, config.box.fit);
      touch();
      refreshGui();
    });
    root.add(config.plane, 'enabled').name('plane');
    root.add(config.plane, 'axis', [...PLANE_AXES]).name('axis');
    offsetCtl = root.add(config.plane, 'offset', -50, 50, 0.01).name('offset (m)');
    root.add(config.plane, 'flip').name('flip');
    root.add(config, 'caps').name('caps');
    root.addColor(config, 'capColor').name('cap colour');
    root.add(config, 'showHandles').name('show handles');
    root.add({ clear: () => api.clear() }, 'clear').name('Clear section');
    root.onChange(() => touch());
  },

  onModel(app: ViewerApp): void {
    config.box.min = config.box.max = null; // the old box belongs to the old model (a lazy refit follows if the box is on)
    pushedAny = false;
    lastPlanes = [];
    foreign = false;
    ownedVersion = app.renderer.clipVersion;
    const b = app.loaded?.geometry.totalBounds();
    if (b && !b.isEmpty() && offsetCtl) {
      const r = Math.max(1, Math.ceil(b.getSize(new Vector3()).length() / 2));
      offsetCtl.min(-r);
      offsetCtl.max(r);
    }
    overlayInvalidate?.();
  },

  onFrame(app: ViewerApp): boolean | void {
    // Nothing enabled and nothing pushed: one comparison per frame, the renderer is left alone.
    if (!config.box.enabled && !config.plane.enabled && !pushedAny) return;
    pushPlanes(app);
  },
};
