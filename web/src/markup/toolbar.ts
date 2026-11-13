// The drawing toolbar: a small floating bar over the viewport, shown only while a sketch (or an issue's viewpoint, which is a
// sketch) is being edited. It holds the drawing tools, colour, line weight, fill, undo and redo of the markup history, and Done.
// DOM only; the tools and the history live in controller.ts. The bar registers its rect with `ov.reserve` (through the view),
// keeps out of the other reserved rects (the gizmo, legends, the status bar and rails) and fits a 390 px phone width.

import type { MarkupController, ToolId } from './controller';
import { TOOLS, toolInfo } from './controller';
import { COLOURS, COLOUR_KEYS } from './model';
import type { ColourKey, Weight } from './model';
import type { Overlay, Rect } from '../ui/overlay';
import { buildViewSwitch } from '../issues/viewSwitchUi';

const STYLE_ID = 'markup-toolbar-styles';
const CSS = `
#markup-float { position: absolute; left: 0; top: 0; z-index: 8; display: none; flex-direction: column; gap: 4px; padding: 5px 6px; border-radius: 12px;
  width: max-content; max-width: calc(100% - 16px); box-sizing: border-box; border: 1px solid #3b9cff; background: rgba(20,32,46,0.96); color: #eaf2ff;
  font: 600 12px system-ui, sans-serif; box-shadow: 0 2px 10px rgba(0,0,0,0.4); }
#markup-float * { box-sizing: border-box; }
#markup-float .mf-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 4px; }
#markup-float button { border: 1px solid #3b6c9c; background: #1c2f45; color: #eaf2ff; border-radius: 8px; font: inherit; cursor: pointer; min-height: 30px; padding: 0 9px; }
#markup-float button:disabled { opacity: 0.4; cursor: default; }
#markup-float button:hover:not(:disabled) { background: #26405e; }
#markup-float .mf-tool { width: 32px; padding: 0; display: inline-flex; align-items: center; justify-content: center; }
#markup-float .mf-tool svg { width: 18px; height: 18px; }
#markup-float .mf-tool[aria-pressed=true] { background: #1f4a7a; border-color: #3b9cff; }
#markup-float .mf-sw { width: 24px; height: 24px; min-height: 24px; border-radius: 50%; padding: 0; border: 2px solid transparent; outline: 1px solid #3b6c9c; }
#markup-float .mf-sw[aria-pressed=true] { border-color: #fff; outline: 2px solid #3b9cff; }
#markup-float .mf-w { width: 28px; padding: 0; display: inline-flex; align-items: center; justify-content: center; }
#markup-float .mf-w[aria-pressed=true] { background: #1f4a7a; border-color: #3b9cff; }
#markup-float .mf-w i { display: block; width: 14px; background: currentColor; border-radius: 2px; }
#markup-float .mf-fill[aria-pressed=true] { background: #1f4a7a; border-color: #3b9cff; }
#markup-float .mf-label { color: #9fc4ee; padding: 0 4px; white-space: nowrap; }
#markup-float .mf-done { background: #1f6fe5; border-color: #3b9cff; }
#markup-float input { background: #0e1218; color: #eaf2ff; border: 1px solid #3b6c9c; border-radius: 6px; padding: 4px 6px; font: 12px system-ui, sans-serif; min-width: 0; width: 100%; max-width: 360px; }
#markup-float .vs-seg { border-radius: 8px; }
#markup-float .vs-seg button { border: 0; border-radius: 0; background: #1c2f45; min-width: 44px; padding: 0 8px; }
#markup-float .vs-seg button + button { border-left: 1px solid #3b6c9c; }
#markup-float .vs-seg button[aria-pressed=true] { background: #1f4a7a; box-shadow: inset 0 -2px 0 #3b9cff; }
@media (max-width: 760px) { #markup-float .mf-tool { width: 30px; } #markup-float button { min-height: 32px; } }
`;

const SVG = (body: string): string =>
  `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round" aria-hidden="true">${body}</svg>`;

export const TOOL_ICONS: Record<ToolId, string> = {
  select: SVG('<path d="M5 3l10 6.5-4.6 1.2L8.2 15.5z"/>'),
  cloud: SVG('<path d="M5.5 14.5a2.4 2.4 0 0 1-.4-4.6 3 3 0 0 1 3.2-3.2 3 3 0 0 1 5.4.6 2.6 2.6 0 0 1 1.4 5 2.6 2.6 0 0 1-3.3 2.2 3 3 0 0 1-3.1.6 2.6 2.6 0 0 1-3.2-.6z"/>'),
  cloudFree: SVG('<path d="M4 13.5a2.2 2.2 0 0 1-.2-4.2 2.8 2.8 0 0 1 3-2.8 2.8 2.8 0 0 1 4.8.4 2.4 2.4 0 0 1 1.2 4.4"/><path d="M11 17l5-5 1.5 1.5-5 5H11z"/>'),
  callout: SVG('<path d="M3 3.5h10v5.5H3z"/><path d="M9 9l5 6"/><circle cx="15" cy="16" r="1.4"/>'),
  text: SVG('<path d="M4 5.5V4h12v1.5M10 4v12M8 16h4"/>'),
  pointer: SVG('<path d="M4 16L15 5M15 5H8.6M15 5v6.4"/><circle cx="4.5" cy="15.5" r="1.2"/>'),
  highlight: SVG('<path d="M4 16h3.5l8-8-3.5-3.5-8 8z"/><path d="M11 6l3.5 3.5M3 18h6" stroke-width="1.2"/>'),
  highlightBox: SVG('<rect x="3.5" y="6" width="13" height="8" fill="currentColor" fill-opacity="0.35"/>'),
  rect: SVG('<rect x="3.5" y="5" width="13" height="10" rx="1"/>'),
  ellipse: SVG('<ellipse cx="10" cy="10" rx="7" ry="5"/>'),
  line: SVG('<path d="M4 16L16 4"/>'),
  arrow: SVG('<path d="M4 16L16 4M16 4H9.5M16 4v6.5"/>'),
  polyline: SVG('<path d="M3.5 15l4-8 4 5 5-7"/>'),
  polygon: SVG('<path d="M4 14.5l3-8.5 9 2.5-2 8z"/>'),
  pen: SVG('<path d="M3.5 15c3-9 5 3 8-4 1.5-3.5 3-3 5-5"/>'),
};

function overlap(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.w - 1 && b.x < a.x + a.w - 1 && a.y < b.y + b.h - 1 && b.y < a.y + a.h - 1;
}

/** Where a bar of `w` x `h` goes: bottom centre inside the insets, moved aside or up where another reserved rect is. */
export function toolbarSpot(ov: Pick<Overlay, 'width' | 'height' | 'insets' | 'reserved'>, w: number, h: number, own: Rect | null): { x: number; y: number } {
  const ins = ov.insets;
  const minX = ins.left + 8;
  const maxX = Math.max(minX, ov.width - ins.right - w - 8);
  const baseY = ov.height - ins.bottom - h - 8;
  const others = ov.reserved.filter((r) => !(own && Math.abs(r.x - own.x) < 1.5 && Math.abs(r.y - own.y) < 1.5 && Math.abs(r.w - own.w) < 1.5 && Math.abs(r.h - own.h) < 1.5));
  let x = Math.min(maxX, Math.max(minX, (ins.left + ov.width - ins.right - w) / 2));
  let y = baseY;
  for (let i = 0; i < 8; i++) {
    const me: Rect = { x, y, w, h };
    const hit = others.find((r) => r.w > 0 && r.h > 0 && overlap(me, r) && !(r.w >= ov.width - 2 && r.h >= ov.height - 2));
    if (!hit) break;
    const left = hit.x - w - 8;
    const right = hit.x + hit.w + 8;
    if (left >= minX) x = left;
    else if (right <= maxX) x = right;
    else y = Math.max(ins.top + 8, hit.y - h - 8);
  }
  return { x, y };
}

export class DrawToolbar {
  readonly root: HTMLDivElement;
  private key = '';
  rect: Rect | null = null;

  constructor(private readonly c: MarkupController, stage: HTMLElement) {
    if (!document.getElementById(STYLE_ID)) {
      const st = document.createElement('style');
      st.id = STYLE_ID;
      st.textContent = CSS;
      document.head.appendChild(st);
    }
    const root = document.createElement('div');
    root.id = 'markup-float';
    root.setAttribute('role', 'toolbar');
    root.setAttribute('aria-label', 'Drawing tools');
    root.setAttribute('data-help-key', 'Drawing toolbar');
    // Keep presses on the bar from reaching the canvas (the view takes pointer input there).
    for (const t of ['pointerdown', 'pointerup', 'mousedown', 'click', 'dblclick', 'wheel']) root.addEventListener(t, (e) => e.stopPropagation());
    stage.appendChild(root);
    this.root = root;
  }

  private build(polyPoints: number, finish: () => void): void {
    const c = this.c;
    const root = this.root;
    const keepText = document.activeElement instanceof HTMLInputElement && root.contains(document.activeElement);
    if (keepText) return; // typing in the text box: the bar stays as it is
    root.textContent = '';
    const mkBtn = (label: string, act: string, fn: () => void, cls = ''): HTMLButtonElement => {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = label;
      b.setAttribute('data-act', act);
      if (cls) b.className = cls;
      b.addEventListener('click', fn);
      return b;
    };
    // Row 1: the tools.
    const tools = document.createElement('div');
    tools.className = 'mf-row';
    tools.setAttribute('data-mf', 'tools');
    for (const t of TOOLS) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'mf-tool';
      b.setAttribute('data-tool-id', t.id);
      b.setAttribute('aria-pressed', String(c.tool === t.id));
      b.setAttribute('aria-label', t.label);
      b.title = `${t.label}: ${t.hint}`;
      b.innerHTML = TOOL_ICONS[t.id];
      b.addEventListener('click', () => c.setTool(t.id === c.tool && t.id !== 'select' ? 'select' : t.id));
      tools.appendChild(b);
    }
    root.appendChild(tools);
    // Row 2: colour, weight, fill.
    const style = document.createElement('div');
    style.className = 'mf-row';
    style.setAttribute('data-mf', 'style');
    for (const k of COLOUR_KEYS) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'mf-sw';
      b.setAttribute('data-colour', k);
      b.setAttribute('aria-pressed', String(c.colour() === k));
      b.setAttribute('aria-label', k);
      b.title = k;
      b.style.background = COLOURS[k as ColourKey];
      b.addEventListener('click', () => c.setColour(k));
      style.appendChild(b);
    }
    ([1, 2, 3, 4] as Weight[]).forEach((w) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'mf-w';
      b.setAttribute('data-weight', String(w));
      b.setAttribute('aria-pressed', String(c.weight === w));
      b.setAttribute('aria-label', `Line weight ${w}`);
      b.title = `Line weight ${w}`;
      const i = document.createElement('i');
      i.style.height = `${[1.5, 2.5, 4, 6][w - 1]}px`;
      b.appendChild(i);
      b.addEventListener('click', () => c.setWeight(w));
      style.appendChild(b);
    });
    const fill = mkBtn('Fill', 'fill', () => c.setFill(!c.fill), 'mf-fill');
    fill.setAttribute('aria-pressed', String(c.fill));
    style.appendChild(fill);
    root.appendChild(style);
    // Row 3 (only for tools that take text): the text of the next callout, text box or pointer.
    const k = toolInfo(c.tool).kind;
    if (k === 'callout' || k === 'text' || k === 'pointer') {
      const row = document.createElement('div');
      row.className = 'mf-row';
      const inp = document.createElement('input');
      inp.type = 'text';
      inp.placeholder = 'Text for the next callout, text box or pointer';
      inp.setAttribute('aria-label', 'Text for the next markup');
      inp.setAttribute('data-act', 'text');
      inp.value = c.text;
      inp.addEventListener('input', () => { c.text = inp.value; });
      inp.addEventListener('keydown', (e) => { e.stopPropagation(); });
      row.appendChild(inp);
      root.appendChild(row);
    }
    // Row 3b (only when the active sketch is tied to a 3D construct): 3D, Plan or Section.
    const vs = c.viewSwitch;
    const sk = c.active;
    if (vs && sk && vs.tied(sk)) {
      const row = document.createElement('div');
      row.className = 'mf-row';
      row.setAttribute('data-mf', 'view');
      row.appendChild(buildViewSwitch({ mode: () => vs.mode(sk), apply: (m) => { vs.apply(sk.id, m); } }, { helpKey: 'Drawing toolbar/View switch' }));
      root.appendChild(row);
    }
    // Row 4: what is being drawn, undo, redo, finish, done.
    const act = document.createElement('div');
    act.className = 'mf-row';
    const label = document.createElement('span');
    label.className = 'mf-label';
    label.setAttribute('data-act', 'label');
    label.textContent = c.active?.title ? `${c.active.title}: ${toolInfo(c.tool).label}` : toolInfo(c.tool).label;
    const undo = mkBtn('Undo', 'undo', () => c.undo());
    undo.disabled = !c.canUndo;
    undo.title = 'Undo the last change (Ctrl+Z)';
    const redo = mkBtn('Redo', 'redo', () => c.redo());
    redo.disabled = !c.canRedo;
    redo.title = 'Redo (Ctrl+Shift+Z)';
    const fin = mkBtn('Finish', 'finish', finish);
    fin.style.display = polyPoints > 0 ? '' : 'none';
    const done = mkBtn('Done', 'done', () => c.setEditing(false), 'mf-done');
    done.title = 'Stop editing the sketch';
    act.append(label, undo, redo, fin, done);
    root.appendChild(act);
  }

  /** Show or hide, rebuild when the state changed, and place the bar. Returns the rect to reserve (canvas px), or null. */
  update(show: boolean, ov: Overlay | null, polyPoints: number, finish: () => void): Rect | null {
    const c = this.c;
    if (!show) {
      this.root.style.display = 'none';
      this.rect = null;
      this.key = '';
      return null;
    }
    const key = [c.tool, c.colour(), c.weight, c.fill, c.canUndo, c.canRedo, polyPoints, c.active?.id, c.active?.title, c.text.length ? 1 : 0, c.viewSwitch?.key(c.active) ?? ''].join('|');
    const shown = this.root.style.display !== 'none';
    if (!shown || key !== this.key) {
      this.key = key;
      this.build(polyPoints, finish);
    } else {
      // The text box keeps what is typed; the undo state may change without a rebuild key change.
      const u = this.root.querySelector<HTMLButtonElement>('[data-act=undo]');
      if (u) u.disabled = !c.canUndo;
    }
    this.root.style.display = 'flex';
    if (!ov) return null;
    // Wrap inside the free width between the edge chrome (a phone has rails at both sides), then measure.
    this.root.style.maxWidth = `${Math.max(160, Math.round(ov.width - ov.insets.left - ov.insets.right - 16))}px`;
    const stage = this.root.offsetParent as HTMLElement | null;
    const cv = c.app.canvas.getBoundingClientRect();
    const st = stage?.getBoundingClientRect();
    const w = this.root.offsetWidth;
    const h = this.root.offsetHeight;
    const spot = toolbarSpot(ov, w, h, this.rect);
    this.root.style.left = `${spot.x + (st ? cv.left - st.left : 0)}px`;
    this.root.style.top = `${spot.y + (st ? cv.top - st.top : 0)}px`;
    this.rect = { x: spot.x, y: spot.y, w, h };
    return this.rect;
  }
}
