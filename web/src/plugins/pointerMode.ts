// Pointer mode plugin: the Arrow (select) and Hand (move) modes of the left mouse button, shown as a two-button toggle on the
// gizmo (plugins/gizmo.ts) and bound to the keys R (arrow) and G (hand). Docs: docs-features/pointer-modes.md.
//
//   hand   left drag orbits, Shift or right drag pans, wheel and pinch zoom, a click selects; cursor grab, grabbing while dragging.
//   arrow  a click selects (Shift adds, Ctrl or Cmd toggles); left drag draws a selection box: left to right is a WINDOW (picks
//          what is fully inside, solid outline), right to left a CROSSING box (picks what it touches, dashed outline);
//          Shift adds, Ctrl or Cmd toggles, Esc cancels. The right and middle buttons and the wheel still move the camera; on
//          touch one finger draws the box and two fingers orbit and zoom. Cursor: the default arrow.
//
// The mode is a per-viewer convenience: localStorage `xray.pointerMode`, no params section, so no share link, saved view,
// preset or packed page carries it.
//
//   window.__xrayPointer = { mode, setMode(m), boxSelect(rect, mode, how?), pick(rect, mode), drawing() }

import { Matrix4 } from 'three';
import type { AppPlugin, ViewerApp } from '../app';
import { registerAction } from '../input/actions';
import { boxModeOf, pickInRect, rectOf } from '../input/boxSelect';
import type { BoxMode, PixelRect } from '../input/boxSelect';
import { configureControls, loadPointerMode, savePointerMode, selectHowOf } from '../input/pointerMode';
import type { PointerMode, SelectHow } from '../input/pointerMode';
import { FLAG_FOCUS, FLAG_HIDDEN } from '../types';

export interface PointerApi {
  readonly mode: PointerMode;
  setMode(m: PointerMode): void;
  /** Ids a box would pick now (canvas pixels), without selecting. */
  pick(rect: PixelRect, mode: BoxMode): number[];
  /** Pick with a box and select the result. Returns the ids. */
  boxSelect(rect: PixelRect, mode: BoxMode, how?: SelectHow): number[];
  /** True while a selection box is being drawn. */
  drawing(): boolean;
}

declare global {
  interface Window {
    __xrayPointer?: PointerApi;
  }
}

/** A drag shorter than this (CSS pixels) is a click. The same slop as the click-to-select in app.ts. */
export const BOX_SLOP = 5;

let mode: PointerMode = 'hand';
const listeners = new Set<() => void>();
let applyMode: (() => void) | null = null;

export function getPointerMode(): PointerMode {
  return mode;
}

export function setPointerMode(m: PointerMode): void {
  if (m === mode) return;
  mode = m;
  try {
    savePointerMode(window.localStorage, m);
  } catch {
    /* no storage */
  }
  applyMode?.();
  for (const l of listeners) l();
}

export function onPointerModeChange(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

const CSS = `
canvas[data-pointer-mode="hand"]{cursor:grab}
canvas[data-pointer-mode="hand"].xp-grabbing{cursor:grabbing}
canvas[data-pointer-mode="arrow"]{cursor:default}
#xray-boxselect{position:absolute;z-index:11;pointer-events:none;box-sizing:border-box;display:none}
#xray-boxselect[data-box="window"]{border:1.5px solid #3b9cff;background:rgba(59,156,255,.14)}
#xray-boxselect[data-box="crossing"]{border:1.5px dashed #5fd38d;background:rgba(95,211,141,.14)}
`;

/** Ids of the elements a box picks now: the visible ones (not hidden, not isolated away, not click-through ghosts). */
function pickIds(app: ViewerApp, rect: PixelRect, boxMode: BoxMode): number[] {
  const els = app.loaded?.model.elements;
  if (!els) return [];
  const { camera, canvas } = app.renderer;
  camera.updateMatrixWorld();
  const vp = new Matrix4().multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse);
  const { alpha, flags } = app.renderer.state;
  const hides = app.settings.overrides.userHides;
  const r = canvas.getBoundingClientRect();
  return pickInRect({
    count: els.length,
    boundsOf: (id) => els[id]?.bounds,
    eligible: (id) => {
      const f = flags[id] ?? 0;
      const a = alpha[id] ?? 1;
      if ((f & FLAG_HIDDEN) !== 0 || a < 0 || hides.has(id)) return false;
      return (f & FLAG_FOCUS) !== 0 || a >= 0.3;
    },
    viewProj: vp.elements,
    width: r.width,
    height: r.height,
    rect,
    mode: boxMode,
    nearW: camera.near,
  });
}

export const pointerModePlugin: AppPlugin = {
  name: 'pointerMode',

  install(app) {
    let store: Storage | null = null;
    try {
      store = window.localStorage;
      store.getItem('xray.probe');
    } catch {
      store = null;
    }
    mode = loadPointerMode(store);
    const canvas = app.canvas;
    const stage = canvas.parentElement ?? document.body;
    const st = document.createElement('style');
    st.id = 'xray-pointer-css';
    st.textContent = CSS;
    document.head.appendChild(st);
    const box = document.createElement('div');
    box.id = 'xray-boxselect';
    box.setAttribute('aria-hidden', 'true');
    stage.appendChild(box);

    // OrbitControls writes `cursor: auto` inline when it connects; that would hide the cursor rules above. Tools that set
    // a cursor of their own (crosshair) still win while they are on, and give it back as ''.
    canvas.style.removeProperty('cursor');
    applyMode = () => {
      configureControls(app.renderer.controls, mode);
      canvas.dataset['pointerMode'] = mode;
      if (mode !== 'arrow') cancelBox();
    };

    // ---- the box
    let drag: { id: number; x: number; y: number; active: boolean; dead: boolean } | null = null;
    const touches = new Set<number>();

    function local(e: PointerEvent): [number, number] {
      const r = canvas.getBoundingClientRect();
      return [e.clientX - r.left, e.clientY - r.top];
    }

    function showBox(rect: PixelRect, bm: BoxMode): void {
      const cr = canvas.getBoundingClientRect();
      const sr = stage.getBoundingClientRect();
      box.style.display = 'block';
      box.style.left = `${cr.left - sr.left + rect.x0}px`;
      box.style.top = `${cr.top - sr.top + rect.y0}px`;
      box.style.width = `${rect.x1 - rect.x0}px`;
      box.style.height = `${rect.y1 - rect.y0}px`;
      box.dataset['box'] = bm;
    }

    function cancelBox(): void {
      drag = null;
      box.style.display = 'none';
    }

    canvas.addEventListener('pointerdown', (e) => {
      if (e.pointerType === 'touch') {
        touches.add(e.pointerId);
        if (touches.size > 1) cancelBox(); // two fingers: the camera, not the box
      }
      if (mode === 'hand') {
        if (e.button === 0) canvas.classList.add('xp-grabbing');
        return;
      }
      if (e.button !== 0 || !e.isPrimary || touches.size > 1) return;
      const [x, y] = local(e);
      drag = { id: e.pointerId, x, y, active: false, dead: false };
    });

    canvas.addEventListener('pointermove', (e) => {
      const d = drag;
      if (!d || e.pointerId !== d.id || d.dead || mode !== 'arrow') return;
      const [x, y] = local(e);
      if (!d.active) {
        if (Math.hypot(x - d.x, y - d.y) <= BOX_SLOP) return;
        d.active = true;
      }
      showBox(rectOf(d.x, d.y, x, y), boxModeOf(d.x, x));
    });

    const finish = (e: PointerEvent): void => {
      if (e.pointerType === 'touch') touches.delete(e.pointerId);
      canvas.classList.remove('xp-grabbing');
      const d = drag;
      if (!d || e.pointerId !== d.id) return;
      drag = null;
      box.style.display = 'none';
      if (e.type !== 'pointerup' || d.dead || !d.active || mode !== 'arrow') return;
      const [x, y] = local(e);
      api.boxSelect(rectOf(d.x, d.y, x, y), boxModeOf(d.x, x), selectHowOf(e));
    };
    canvas.addEventListener('pointerup', finish);
    canvas.addEventListener('pointercancel', finish);
    window.addEventListener('pointerup', () => canvas.classList.remove('xp-grabbing'));
    window.addEventListener('blur', cancelBox);

    // Esc cancels the box before anything else sees it (the Esc that clears the selection included).
    window.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape' || !drag || !drag.active) return;
      drag.dead = true;
      box.style.display = 'none';
      e.stopImmediatePropagation();
      e.preventDefault();
    }, true);

    const api: PointerApi = {
      get mode() {
        return mode;
      },
      setMode: setPointerMode,
      pick: (rect, bm) => pickIds(app, rect, bm),
      boxSelect(rect, bm, how = 'replace') {
        const ids = pickIds(app, rect, bm);
        app.selectWith(ids, how);
        return ids;
      },
      drawing: () => !!drag?.active && !drag.dead,
    };
    window.__xrayPointer = api;

    registerAction({
      id: 'pointer.select',
      label: 'Arrow mode: click selects, drag draws a selection box',
      group: 'Modes',
      keys: ['r'],
      description: 'Left to right picks what is inside the box, right to left picks what it touches. Shift adds, Ctrl toggles, Esc cancels.',
      run: () => setPointerMode('arrow'),
    });
    registerAction({
      id: 'pointer.hand',
      label: 'Hand mode: drag moves the camera',
      group: 'Modes',
      keys: ['g'],
      description: 'Left drag orbits, Shift or right drag pans, wheel zooms. A click still selects.',
      run: () => setPointerMode('hand'),
    });
    applyMode();
  },
};
