// Gizmo plugin: an on-screen navigation cube with roll, quarter-turn, home and projection buttons, plus a compact section
// strip (planes X / Y / Z, box fitted to the selection, flip, caps, clear) in the bottom-right corner of the stage, and
// direct-manipulation handles for the section plane (src/gizmo/planeHandles.ts). Docs: docs-features/gizmo.md.
//
//   window.__xrayGizmo = { state, setVisible(v), setCollapsed(v), lookFrom(region), roll(sign), turn(sign), home(), handles }

import { Box3, Vector3 } from 'three';
import type { AppPlugin, ViewerApp } from '../app';
import { getAction, registerAction, runAction } from '../input/actions';
import { formatChord, getKeymap } from '../input/keymap';
import { isPseudoOrtho, navSettings, pushHistory } from '../input/navigation';
import { cancelGizmoMove, currentView, isGizmoMoving, frameFrom, gizmoCameraFrame, orbitCamera, turnTo } from '../gizmo/camera';
import { createCubeView } from '../gizmo/cubeView';
import type { CubeView } from '../gizmo/cubeView';
import { installPlaneHandles } from '../gizmo/planeHandles';
import type { PlaneHandles } from '../gizmo/planeHandles';
import { isVertical, naturalUp, normalize, regionName, regionNear, regionView, rollView, rotateAbout, turnView } from '../gizmo/maths';
import type { Region, V3, View } from '../gizmo/maths';
import type { SectionApi } from './section';
import { registerParamSection } from '../ui/params';

export interface GizmoState {
  visible: boolean;
  collapsed: boolean;
}

export interface GizmoApi {
  state: GizmoState;
  setVisible(v: boolean): void;
  setCollapsed(v: boolean): void;
  lookFrom(r: Region): void;
  roll(sign: 1 | -1): void;
  turn(sign: 1 | -1): void;
  home(): void;
  /** True while a gizmo camera move runs. */
  isMoving(): boolean;
  handles: PlaneHandles | null;
}

declare global {
  interface Window {
    __xrayGizmo?: GizmoApi;
  }
}

const STORAGE_KEY = 'xray.gizmo';
const state: GizmoState = { visible: true, collapsed: false };
let appRef: ViewerApp | null = null;
let root: HTMLDivElement | null = null;
let cube: CubeView | null = null;
let handles: PlaneHandles | null = null;
let lastSig = '';
let lastButtons = 0;
let lastFit = 0;
let refreshButtons: (() => void) | null = null;
let guiShow: { updateDisplay(): unknown } | null = null;

function isPhone(): boolean {
  try {
    return window.matchMedia('(max-width: 700px)').matches;
  } catch {
    return false; // no matchMedia
  }
}

/** Factory state, also what "Reset to defaults" restores: shown, expanded on a desktop, collapsed on a phone. */
export function gizmoFactoryState(phone: boolean): GizmoState {
  return { visible: true, collapsed: phone };
}

function load(): void {
  const phone = isPhone();
  state.collapsed = phone;
  try {
    const v = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? 'null') as Partial<GizmoState> | null;
    if (v && typeof v.visible === 'boolean') state.visible = v.visible;
    if (v && typeof v.collapsed === 'boolean' && !phone) state.collapsed = v.collapsed;
  } catch {
    /* private mode or corrupt: defaults */
  }
}

function save(): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* ignore */
  }
}

function section(): SectionApi | null {
  return window.__xraySection ?? null;
}

// ---------------------------------------------------------------- shortcuts in tooltips

function keysOf(id: string): string {
  const km = getKeymap();
  const list = km ? km.bindingsOf(id) : (getAction(id)?.keys ?? []);
  return list.map(formatChord).join(', ');
}

function withKeys(text: string, ...ids: string[]): string {
  const k = ids.map(keysOf).filter(Boolean).join('; ');
  return k ? `${text} (${k})` : text;
}

const FACE_ACTION: Record<string, string> = {
  '0,0,1': 'view.front', '0,0,-1': 'view.back', '1,0,0': 'view.right', '-1,0,0': 'view.left', '0,1,0': 'view.top', '0,-1,0': 'view.bottom', '1,1,1': 'view.iso',
};

// ---------------------------------------------------------------- camera commands

function boxOfIds(app: ViewerApp, ids: Iterable<number>): Box3 {
  const box = new Box3();
  const els = app.loaded?.model.elements;
  if (!els) return box;
  for (const id of ids) {
    const b = els[id]?.bounds;
    if (b) box.union(new Box3(new Vector3(b[0], b[1], b[2]), new Vector3(b[3], b[4], b[5])));
  }
  return box;
}

/** The selection, else the whole model: what the views frame. */
function workBox(app: ViewerApp): Box3 {
  const sel = app.controller?.selection;
  if (sel && sel.size > 0) {
    const b = boxOfIds(app, sel);
    if (!b.isEmpty()) return b;
  }
  return app.loaded?.geometry.totalBounds() ?? new Box3();
}

function lookFrom(r: Region): void {
  const app = appRef;
  if (!app?.loaded) return;
  const v = regionView(r);
  const f = frameFrom(app, workBox(app), v.direction);
  turnTo(app, v, f?.target, f?.distance);
}

/** The current view, snapped to the nearest cube region and quarter-turn up when it is within 1 degree. */
function snappedView(app: ViewerApp): View {
  const v = currentView(app);
  const r = regionNear(v.direction, 1);
  if (!r) return v;
  const direction = regionView(r).direction;
  // Snap the up to the nearest of the 4 quarter turns of the region's natural up.
  let best = naturalUp(direction);
  let bestDot = -2;
  let u: View = { direction, up: best };
  for (let i = 0; i < 4; i++) {
    const d = u.up[0] * v.up[0] + u.up[1] * v.up[1] + u.up[2] * v.up[2];
    if (d > bestDot) {
      bestDot = d;
      best = u.up;
    }
    u = rollView(u, 1);
  }
  return { direction, up: best };
}

function roll(sign: 1 | -1): void {
  const app = appRef;
  if (!app) return;
  turnTo(app, rollView(snappedView(app), sign));
}

function turn(sign: 1 | -1): void {
  const app = appRef;
  if (!app) return;
  turnTo(app, turnView(snappedView(app), sign));
}

/** Frame the whole model from the default corner (the pose of app.frameAll), eased. */
function home(): void {
  const app = appRef;
  if (!app) return;
  const { camera, controls } = app.renderer;
  const pos = camera.position.clone();
  const tgt = controls.target.clone();
  const up = camera.up.clone();
  pushHistory(app, 'gizmo');
  camera.up.set(0, 1, 0);
  app.frameAll(); // sets near, far and the distance limits, and the home pose
  const homePos = camera.position.clone();
  const homeTarget = controls.target.clone();
  camera.position.copy(pos);
  controls.target.copy(tgt);
  camera.up.copy(up);
  controls.update();
  const dir = normalize([homePos.x - homeTarget.x, homePos.y - homeTarget.y, homePos.z - homeTarget.z]);
  turnTo(app, { direction: dir, up: naturalUp(dir) }, homeTarget, homePos.distanceTo(homeTarget));
}

// ---------------------------------------------------------------- DOM

const CSS = `
#xray-gizmo{position:absolute;right:10px;bottom:30px;z-index:12;display:flex;align-items:flex-end;gap:6px;color:#dfe6ee;
  font:600 11px/1 system-ui,-apple-system,'Segoe UI',sans-serif;user-select:none;-webkit-user-select:none;pointer-events:none}
#xray-gizmo[hidden]{display:none}
#xray-gizmo > *{pointer-events:auto}
#xray-gizmo .xg-sec{display:grid;grid-template-columns:repeat(2,26px);gap:3px;padding:4px;background:rgba(20,24,32,.82);border:1px solid #2d3748;border-radius:6px}
#xray-gizmo .xg-btn{box-sizing:border-box;width:26px;height:24px;padding:0;display:flex;align-items:center;justify-content:center;background:#1b2230;
  border:1px solid #2d3748;border-radius:4px;color:inherit;font:inherit;cursor:pointer}
#xray-gizmo .xg-btn svg{width:14px;height:14px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
#xray-gizmo .xg-btn:hover:not(:disabled){background:#243049;border-color:#3a4a66}
#xray-gizmo .xg-btn[aria-pressed=true]{background:#1f4a7a;border-color:#3b9cff;color:#fff}
#xray-gizmo .xg-btn:disabled{opacity:.4;cursor:default}
#xray-gizmo .xg-btn.xg-foreign{background:#5a4214;border-color:#e0a83a;color:#ffd27a}
#xray-gizmo .xg-btn:focus-visible,#xray-gizmo .xg-cell:focus-visible{outline:2px solid #3b9cff;outline-offset:1px}
#xray-gizmo .xg-ax-x{color:#ff8a80}#xray-gizmo .xg-ax-y{color:#7ee2a8}#xray-gizmo .xg-ax-z{color:#85c1e9}
#xray-gizmo .xg-btn[aria-pressed=true].xg-ax-x,#xray-gizmo .xg-btn[aria-pressed=true].xg-ax-y,#xray-gizmo .xg-btn[aria-pressed=true].xg-ax-z{color:#fff}
#xray-gizmo .xg-nav{position:relative;width:132px;height:154px}
#xray-gizmo .xg-cube{position:absolute;left:6px;top:4px;cursor:grab;touch-action:none;overflow:visible}
#xray-gizmo .xg-cube.dragging{cursor:grabbing}
#xray-gizmo .xg-cell{fill:hsl(212 14% calc(var(--lit,80) * 1%));stroke:#4f5a69;stroke-width:.7;cursor:pointer;outline:none}
#xray-gizmo .xg-cell.xg-edge,#xray-gizmo .xg-cell.xg-corner{fill:hsl(212 14% calc((var(--lit,80) - 7) * 1%))}
#xray-gizmo .xg-cell.current{fill:#8fc1f2}
#xray-gizmo .xg-cell.hover{fill:#3b9cff}
#xray-gizmo .xg-label{fill:#141820;font-weight:700;font-family:system-ui,-apple-system,'Segoe UI',sans-serif}
#xray-gizmo .xg-nav .xg-btn{position:absolute;width:24px;height:22px;background:rgba(27,34,48,.88)}
#xray-gizmo .xg-rccw{left:0;top:0}#xray-gizmo .xg-rcw{right:0;top:0}
#xray-gizmo .xg-tl{left:0;top:98px}#xray-gizmo .xg-tr{right:0;top:98px}
#xray-gizmo .xg-home{left:26px;bottom:0}#xray-gizmo .xg-proj{left:54px;bottom:0}#xray-gizmo .xg-min{left:82px;bottom:0}
#xray-gizmo .xg-open{display:none;width:34px;height:32px;border-radius:6px;background:rgba(27,34,48,.92)}
#xray-gizmo .xg-open svg{width:20px;height:20px}
#xray-gizmo.collapsed .xg-sec,#xray-gizmo.collapsed .xg-nav{display:none}
#xray-gizmo.collapsed .xg-open{display:flex}
@media (max-width:700px){#xray-gizmo{right:36px}}
/* Not enough room beside an open tool drawer (fitLayout): drop the section strip, then show only the cube button, then hide. */
#xray-gizmo.fit-nav:not(.peek) .xg-sec{display:none}
#xray-gizmo.fit-button:not(.peek) .xg-sec,#xray-gizmo.fit-button:not(.peek) .xg-nav{display:none}
#xray-gizmo.fit-button:not(.peek) .xg-open{display:flex}
#xray-gizmo.fit-none:not(.peek){display:none}
#xray-gizmo.peek{z-index:15}
`;

const I = (body: string): string => `<svg viewBox="0 0 16 16" aria-hidden="true">${body}</svg>`;
const ICONS = {
  rollCw: I('<path d="M12.6 9.2A4.8 4.8 0 1 1 11 4.3"/><path d="M11.6 1.6 11 4.3 13.7 5"/>'),
  rollCcw: I('<path d="M3.4 9.2A4.8 4.8 0 1 0 5 4.3"/><path d="M4.4 1.6 5 4.3 2.3 5"/>'),
  turnL: I('<path d="M14 7.5c0 1.9-2.7 3.4-6 3.4S2 9.4 2 7.5"/><path d="M14 7.5C14 5.6 11.3 4 8 4"/><path d="M4.2 9 2 7.5 1.4 10"/>'),
  turnR: I('<path d="M2 7.5c0 1.9 2.7 3.4 6 3.4s6-1.5 6-3.4"/><path d="M2 7.5C2 5.6 4.7 4 8 4"/><path d="M11.8 9 14 7.5 14.6 10"/>'),
  home: I('<path d="M2.5 8 8 3l5.5 5"/><path d="M4 7v6h3v-3.5h2V13h3V7"/>'),
  proj: I('<path d="M3 4h10v8H3z"/><path d="M3 4l3 2.2h4L13 4M3 12l3-2.2h4l3 2.2M6 6.2v3.6M10 6.2v3.6"/>'),
  min: I('<path d="M4 8h8"/>'),
  cube: I('<path d="M8 1.8 13.5 5v6L8 14.2 2.5 11V5z"/><path d="M2.5 5 8 8.2 13.5 5M8 8.2v6"/>'),
  box: I('<path d="M3 5.5 8 3l5 2.5v5L8 13l-5-2.5z" stroke-dasharray="2 1.6"/><path d="M3 5.5 8 8l5-2.5M8 8v5"/>'),
  flip: I('<path d="M2 8h12"/><path d="M8 2v4M6.2 4 8 6l1.8-2M8 14v-4M6.2 12 8 10l1.8 2"/>'),
  caps: I('<path d="M3 3h10v10H3z"/><path d="M3 9l6-6M3 13 13 3M7 13l6-6"/>'),
  clear: I('<path d="M4 4l8 8M12 4l-8 8"/>'),
};

function btn(cls: string, html: string, label: string, help: string, onClick: () => void): HTMLButtonElement {
  const b = document.createElement('button');
  b.type = 'button';
  b.className = `xg-btn ${cls}`;
  b.innerHTML = html;
  b.setAttribute('aria-label', label);
  b.setAttribute('data-help-key', help);
  b.setAttribute('data-help-title', label);
  b.addEventListener('click', (e) => {
    e.stopPropagation();
    onClick();
  });
  return b;
}

/** Centre of the selection, else of the model. */
function focusCentre(app: ViewerApp): [number, number, number] | null {
  const b = workBox(app);
  if (b.isEmpty()) return null;
  const c = b.getCenter(new Vector3());
  return [c.x, c.y, c.z];
}

function setPlaneAxis(axis: 'x' | 'y' | 'z'): void {
  const s = section();
  const app = appRef;
  if (!s || !app?.loaded) return;
  const c = s.config;
  if (c.plane.enabled && c.plane.axis === axis) {
    s.set({ plane: { enabled: false } });
    return;
  }
  const a = axis === 'x' ? 0 : axis === 'y' ? 1 : 2;
  const fc = focusCentre(app);
  const offset = fc ? fc[a]! - s.centre()[a]! : 0;
  s.set({ plane: { enabled: true, axis, offset, flip: false } });
}

function build(app: ViewerApp): void {
  const stage = app.canvas.parentElement ?? document.body;
  if (!document.getElementById('xray-gizmo-css')) {
    const st = document.createElement('style');
    st.id = 'xray-gizmo-css';
    st.textContent = CSS;
    document.head.appendChild(st);
  }
  const el = document.createElement('div');
  el.id = 'xray-gizmo';
  el.setAttribute('role', 'toolbar');
  el.setAttribute('aria-label', 'View cube and section tools');
  root = el;

  // Section strip.
  const sec = document.createElement('div');
  sec.className = 'xg-sec';
  sec.setAttribute('role', 'group');
  sec.setAttribute('aria-label', 'Section tools');
  const px = btn('xg-ax-x', 'X', 'Section plane X', 'Gizmo/Plane X', () => setPlaneAxis('x'));
  const py = btn('xg-ax-y', 'Y', 'Section plane Y, horizontal plan cut', 'Gizmo/Plane Y', () => setPlaneAxis('y'));
  const pz = btn('xg-ax-z', 'Z', 'Section plane Z', 'Gizmo/Plane Z', () => setPlaneAxis('z'));
  const bx = btn('', ICONS.box, 'Section box fitted to the selection', 'Gizmo/Section box', () => {
    const s = section();
    if (!s) return;
    if (s.config.box.enabled) s.set({ box: { enabled: false } });
    else s.fitToSelection();
  });
  const fl = btn('', ICONS.flip, 'Flip the section plane', 'Gizmo/Flip plane', () => {
    const s = section();
    if (s) s.set({ plane: { flip: !s.config.plane.flip } });
  });
  const cp = btn('', ICONS.caps, 'Caps on cut solids', 'Gizmo/Caps', () => {
    const s = section();
    if (s) s.set({ caps: !s.config.caps });
  });
  const cl = btn('', ICONS.clear, 'Clear the section', 'Gizmo/Clear section', () => section()?.clear());
  // Column order: X Flip / Y Caps / Z Box / Clear.
  sec.append(px, fl, py, cp, pz, bx, cl);

  // Navigation cube and its buttons.
  const nav = document.createElement('div');
  nav.className = 'xg-nav';
  cube = createCubeView();
  cube.svg.setAttribute('data-help-key', 'Gizmo/View cube');
  cube.svg.setAttribute('data-help-title', 'View cube');
  nav.appendChild(cube.svg);
  const rccw = btn('xg-rccw', ICONS.rollCcw, 'Roll the view 90 degrees counter-clockwise', 'Gizmo/Roll counter-clockwise', () => roll(-1));
  const rcw = btn('xg-rcw', ICONS.rollCw, 'Roll the view 90 degrees clockwise', 'Gizmo/Roll clockwise', () => roll(1));
  const tl = btn('xg-tl', ICONS.turnL, 'Turn 90 degrees left about the vertical', 'Gizmo/Turn left', () => turn(-1));
  const tr = btn('xg-tr', ICONS.turnR, 'Turn 90 degrees right about the vertical', 'Gizmo/Turn right', () => turn(1));
  const hm = btn('xg-home', ICONS.home, 'Home: frame the whole model', 'Gizmo/Home', home);
  const pj = btn('xg-proj', ICONS.proj, 'Orthographic projection', 'Gizmo/Projection', () => {
    runAction(app, 'view.projection');
    refreshButtons?.();
  });
  const mn = btn('xg-min', ICONS.min, 'Collapse the gizmo', 'Gizmo/Collapse', () => {
    if (peek) {
      peek = false; // back beside the drawer
      applyState();
    } else setCollapsed(true);
  });
  nav.append(rccw, rcw, tl, tr, hm, pj, mn);
  const open = btn('xg-open', ICONS.cube, 'Open the view cube and section tools', 'Gizmo/Open gizmo', () => {
    if (fit !== 'full' && fit !== 'nav') peek = true; // no room beside the drawer: open over it
    setCollapsed(false);
  });
  el.append(sec, nav, open);
  stage.appendChild(el);

  const titles = (): void => {
    px.title = 'Section plane X through the selection or model centre. Click again to remove it';
    py.title = withKeys('Section plane Y: horizontal plan cut through the selection or model centre. Alt+C toggles the plane', 'section.togglePlane');
    pz.title = 'Section plane Z through the selection or model centre. Click again to remove it';
    bx.title = withKeys('Section box fitted to the selection, else the model. C toggles the box', 'section.fitSelection', 'section.toggleBox');
    fl.title = 'Keep the other side of the section plane';
    cp.title = 'Paint flat hatched caps on cut solids';
    cl.title = withKeys('Remove the section box and the section plane', 'section.clear');
    rccw.title = withKeys('Roll the view 90 degrees counter-clockwise', 'gizmo.rollCcw');
    rcw.title = withKeys('Roll the view 90 degrees clockwise', 'gizmo.rollCw');
    tl.title = withKeys('Turn 90 degrees left about the vertical', 'gizmo.turnLeft');
    tr.title = withKeys('Turn 90 degrees right about the vertical', 'gizmo.turnRight');
    hm.title = withKeys('Frame the whole model from the home corner', 'view.frameAll');
    pj.title = withKeys('Perspective or orthographic projection', 'view.projection');
    mn.title = withKeys('Collapse to a small button', 'gizmo.toggle');
    open.title = withKeys('Open the view cube and section tools', 'gizmo.toggle');
    for (const p of Array.from(cube!.svg.querySelectorAll<SVGPolygonElement>('[data-region]'))) {
      const r = cube!.regionOf(p);
      if (!r) continue;
      const id = FACE_ACTION[r.join(',')];
      const name = `${regionName(r)} view`;
      const text = id ? withKeys(name, id) : name;
      p.setAttribute('aria-label', text);
    }
  };
  titles();
  el.addEventListener('pointerenter', titles);
  el.addEventListener('focusin', titles);

  refreshButtons = (): void => {
    const s = section();
    const c = s?.config;
    // Planes of a BCF viewpoint are in force: the section settings are not what the view shows, so nothing is lit but
    // Clear, which is marked and says how many planes it removes.
    const foreign = s?.foreignPlanes?.() ?? 0;
    const own = !!c && !foreign;
    const pressed = (b: HTMLButtonElement, v: boolean): void => b.setAttribute('aria-pressed', String(v));
    pressed(px, own && c!.plane.enabled && c!.plane.axis === 'x');
    pressed(py, own && c!.plane.enabled && c!.plane.axis === 'y');
    pressed(pz, own && c!.plane.enabled && c!.plane.axis === 'z');
    pressed(bx, own && c!.box.enabled);
    pressed(fl, own && c!.plane.enabled && c!.plane.flip);
    fl.disabled = !own || !c!.plane.enabled;
    pressed(cp, !!c?.caps);
    cl.disabled = !c || (!c.box.enabled && !c.plane.enabled && !(app.renderer.getClipPlanes()?.length));
    cl.classList.toggle('xg-foreign', foreign > 0);
    cl.setAttribute('aria-label', foreign ? `Clear the ${foreign} clip plane${foreign === 1 ? '' : 's'} of the BCF viewpoint` : 'Clear the section');
    if (foreign) cl.title = `${foreign} clip plane${foreign === 1 ? '' : 's'} from a BCF viewpoint in force. Click to remove them`;
    else if (cl.title.includes('BCF viewpoint')) titles();
    pressed(pj, isPseudoOrtho());
    pj.setAttribute('aria-label', isPseudoOrtho() ? 'Orthographic projection, on' : 'Orthographic projection, off');
  };
  section()?.onChange(() => refreshButtons?.());
  refreshButtons();

  // Cube: click a cell to look from there, drag to orbit.
  let down: { x: number; y: number; lx: number; ly: number; id: number; moved: boolean; region: Region | null } | null = null;
  const svg = cube.svg;
  svg.addEventListener('pointerdown', (ev) => {
    if (ev.button !== 0) return;
    ev.preventDefault();
    ev.stopPropagation();
    try { svg.setPointerCapture(ev.pointerId); } catch { /* synthetic */ }
    down = { x: ev.clientX, y: ev.clientY, lx: ev.clientX, ly: ev.clientY, id: ev.pointerId, moved: false, region: cube!.regionOf(ev.target) };
  });
  svg.addEventListener('pointermove', (ev) => {
    if (!down) {
      cube?.hover(cube.regionOf(ev.target));
      return;
    }
    if (!down.moved && Math.hypot(ev.clientX - down.x, ev.clientY - down.y) > 4) {
      down.moved = true;
      svg.classList.add('dragging');
      cube?.hover(null);
      pushHistory(app, 'gizmo-orbit');
    }
    if (down.moved) {
      const k = 0.012;
      orbitCamera(app, -(ev.clientX - down.lx) * k, -(ev.clientY - down.ly) * k);
    }
    down.lx = ev.clientX;
    down.ly = ev.clientY;
  });
  const up = (ev: PointerEvent): void => {
    if (!down) return;
    const d = down;
    down = null;
    svg.classList.remove('dragging');
    try { svg.releasePointerCapture(ev.pointerId); } catch { /* released */ }
    if (!d.moved && ev.type === 'pointerup' && d.region) lookFrom(d.region);
  };
  svg.addEventListener('pointerup', up);
  svg.addEventListener('pointercancel', up);
  svg.addEventListener('pointerleave', () => {
    if (!down) cube?.hover(null);
  });
  svg.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    const r = cube?.regionOf(ev.target);
    if (!r) return;
    ev.preventDefault();
    ev.stopPropagation();
    lookFrom(r);
  });
  // Stop the wheel from reaching the page; the cube is not a zoom target.
  el.addEventListener('wheel', (e) => e.preventDefault(), { passive: false });

  applyState();
}

function applyState(): void {
  if (!root) return;
  root.hidden = !state.visible;
  root.classList.toggle('collapsed', state.collapsed);
  for (const f of ['nav', 'button', 'none'] as const) root.classList.toggle(`fit-${f}`, fit === f);
  root.classList.toggle('peek', peek && !state.collapsed);
  lastSig = '';
  guiShow?.updateDisplay();
}

// ---------------------------------------------------------------- room beside the tool drawer

type Fit = 'full' | 'nav' | 'button' | 'none';
/** How much of the gizmo fits between the open tool drawer (or the strip) and the right edge of the stage. */
let fit: Fit = 'full';
/** Opened from the cube button while there is no room: drawn over the drawer until the drawer closes or "-". */
let peek = false;
const FULL_W = 65 + 6 + 132;
const NAV_W = 132;
const BTN_W = 34;

function fitLayout(): void {
  const stage = root?.parentElement;
  if (!root || !stage || !state.visible) return;
  const sr = stage.getBoundingClientRect();
  if (!sr.width) return;
  const right = parseFloat(getComputedStyle(root).right) || 10;
  let left = sr.left;
  for (const sel of ['#xray-toolbar', '#xray-toolbar-drawer']) {
    const e = document.querySelector<HTMLElement>(sel);
    if (!e || e.classList.contains('hidden') || e.getClientRects().length === 0) continue;
    left = Math.max(left, e.getBoundingClientRect().right);
  }
  const free = sr.right - right - left - 8;
  const next: Fit = free >= FULL_W ? 'full' : free >= NAV_W ? 'nav' : free >= BTN_W ? 'button' : 'none';
  if (next === fit) return;
  fit = next;
  if (fit === 'full') peek = false;
  applyState();
}

function setVisible(v: boolean): void {
  state.visible = v;
  save();
  applyState();
}

function setCollapsed(v: boolean): void {
  state.collapsed = v;
  save();
  applyState();
  // Keep the keyboard focus inside the gizmo.
  const target = root?.querySelector<HTMLButtonElement>(v ? '.xg-open' : '.xg-min');
  if (target && root?.contains(document.activeElement)) target.focus();
}

function redrawCube(app: ViewerApp): void {
  if (!cube || !root || root.hidden || state.collapsed) return;
  const q = app.renderer.camera.quaternion;
  const sig = `${q.x.toFixed(5)},${q.y.toFixed(5)},${q.z.toFixed(5)},${q.w.toFixed(5)}`;
  if (sig === lastSig) return;
  lastSig = sig;
  const v = currentView(app);
  const r = regionNear(v.direction, 1);
  cube.draw(v, r);
}

// ---------------------------------------------------------------- unroll on orbit

const UNROLL_MS = 160;
let orbitDown: { x: number; y: number } | null = null;
/** Running unroll: the roll angle (about the view axis, from the natural up) at the start. */
let unroll: { start: number; theta0: number } | null = null;

function viewDir(app: ViewerApp): V3 {
  const { camera, controls } = app.renderer;
  return normalize([camera.position.x - controls.target.x, camera.position.y - controls.target.y, camera.position.z - controls.target.z]);
}

function startUnroll(app: ViewerApp, now: number): void {
  const up = app.renderer.camera.up;
  if (Math.abs(up.y - 1) < 1e-9) return;
  const d = viewDir(app);
  if (isVertical(d, 1e-3)) {
    up.set(0, 1, 0);
    return;
  }
  const t = naturalUp(d);
  const u: V3 = [up.x, up.y, up.z];
  const c: V3 = [t[1] * u[2] - t[2] * u[1], t[2] * u[0] - t[0] * u[2], t[0] * u[1] - t[1] * u[0]];
  const theta0 = Math.atan2(c[0] * d[0] + c[1] * d[1] + c[2] * d[2], t[0] * u[0] + t[1] * u[1] + t[2] * u[2]);
  if (!navSettings.smoothMoves || Math.abs(theta0) < 1e-6) {
    up.set(0, 1, 0);
    return;
  }
  unroll = { start: now, theta0 };
}

/** Per frame: ease camera.up from the rolled up to world up about the (moving) view axis. True while it runs. */
function unrollFrame(app: ViewerApp, now: number): boolean {
  const u = unroll;
  if (!u) return false;
  if (isGizmoMoving()) {
    unroll = null; // a cube click took over
    return false;
  }
  const up = app.renderer.camera.up;
  const k = Math.min(1, Math.max(0, (now - u.start) / UNROLL_MS));
  const d = viewDir(app);
  if (k >= 1 || isVertical(d, 1e-3)) {
    unroll = null;
    up.set(0, 1, 0);
    return true;
  }
  const e = 1 - (1 - k) * (1 - k); // ease out
  const r = rotateAbout(naturalUp(d), d, (1 - e) * u.theta0);
  up.set(r[0], r[1], r[2]);
  return true;
}

// ---------------------------------------------------------------- plugin

const api: GizmoApi = {
  state,
  setVisible,
  setCollapsed,
  lookFrom,
  roll,
  turn,
  home,
  isMoving: isGizmoMoving,
  get handles() {
    return handles;
  },
};

export const gizmoPlugin: AppPlugin = {
  name: 'gizmo',

  install(app) {
    appRef = app;
    load();
    window.__xrayGizmo = api;
    registerAction({ id: 'gizmo.toggle', label: 'Gizmo: show or hide the view cube and section strip', group: 'Panels', keys: ['v'], run: () => setVisible(!state.visible) });
    registerAction({ id: 'gizmo.rollCw', label: 'Roll the view 90 degrees clockwise', group: 'Views', keys: [], run: () => roll(1) });
    registerAction({ id: 'gizmo.rollCcw', label: 'Roll the view 90 degrees counter-clockwise', group: 'Views', keys: [], run: () => roll(-1) });
    registerAction({ id: 'gizmo.turnLeft', label: 'Turn 90 degrees left about the vertical', group: 'Views', keys: [], run: () => turn(-1) });
    registerAction({ id: 'gizmo.turnRight', label: 'Turn 90 degrees right about the vertical', group: 'Views', keys: [], run: () => turn(1) });
    registerParamSection('gizmo', {
      share: false,
      collect: () => ({ visible: state.visible, collapsed: state.collapsed }),
      // Not the state after the first model: that comes from localStorage (a gizmo hidden in an earlier visit).
      factory: () => gizmoFactoryState(isPhone()),
      apply(value, bad, path) {
        if (value === null || typeof value !== 'object') {
          bad.push(path);
          return;
        }
        const v = value as Record<string, unknown>;
        for (const [k, x] of Object.entries(v)) {
          if ((k === 'visible' || k === 'collapsed') && typeof x === 'boolean') state[k] = x;
          else bad.push(`${path}.${k}`);
        }
        save();
        applyState();
      },
    });
    build(app);
    const s = section();
    if (s) handles = installPlaneHandles(app, s);
    // A pointer on the canvas takes the camera back from a running gizmo move.
    app.canvas.addEventListener('pointerdown', (e) => {
      cancelGizmoMove();
      orbitDown = e.button === 0 ? { x: e.clientX, y: e.clientY } : null;
    });
    app.canvas.addEventListener('wheel', () => cancelGizmoMove(), { passive: true });
    // The orbit controls turn about world Y: a rolled view (cube roll buttons, an interrupted move) eases back to world up
    // as soon as a mouse orbit starts, so the drag feels like the usual turntable.
    app.canvas.addEventListener('pointermove', (e) => {
      if (!orbitDown || !(e.buttons & 1)) return;
      if (Math.hypot(e.clientX - orbitDown.x, e.clientY - orbitDown.y) < 3) return;
      orbitDown = null;
      startUnroll(app, performance.now());
    });
    window.addEventListener('pointerup', () => (orbitDown = null));

    const gui = app.panel;
    if (gui) {
      const f = gui.addFolder('Gizmo');
      f.close();
      guiShow = f.add(state, 'visible').name('show').onChange((v: boolean) => setVisible(v));
    }
  },

  onModel() {
    lastSig = '';
    refreshButtons?.();
  },

  onFrame(app, now) {
    const moved = gizmoCameraFrame(app, now);
    return unrollFrame(app, now) || moved;
  },

  afterFrame(app, now) {
    redrawCube(app);
    if (now - lastFit > 150) {
      lastFit = now;
      fitLayout();
    }
    if (now - lastButtons > 400) {
      lastButtons = now;
      refreshButtons?.(); // the projection and the planes can change by key or by a BCF viewpoint
    }
  },
};
