// DOM for the action panel: a 44 px icon strip docked at the left edge of #stage and a drawer beside it.
// No tool knowledge here: plugins/toolbar.ts feeds it tools and handles the actions.

import type { ViewerApp } from '../app';
import type { XrayTool } from '../tools/registry';
import { clampDrawerWidth } from '../tools/toolbarModel';
import { getKeymap } from '../input/keymap';
import { el } from './dom';

export const STRIP_W = 44;
export const DRAWER_W = 320;

const CSS = `
.xt-strip{position:absolute;left:0;top:0;bottom:0;width:${STRIP_W}px;z-index:15;box-sizing:border-box;display:flex;flex-direction:column;align-items:center;gap:4px;padding:6px 0;
  background:var(--sb-bg,#141820);color:var(--sb-fg,#dfe6ee);border-right:1px solid var(--sb-line,#262d3a);font:12px/1.35 system-ui,-apple-system,'Segoe UI',sans-serif;overflow:visible}
.xt-strip.hidden,.xt-drawer.hidden{display:none}
.xt-btn-tool{position:relative;width:34px;height:34px;padding:0;display:flex;align-items:center;justify-content:center;background:transparent;color:#aab6c5;border:1px solid transparent;border-radius:6px;cursor:pointer}
.xt-btn-tool:hover{background:var(--sb-hover,#1c2230);color:var(--sb-fg,#dfe6ee)}
.xt-btn-tool.active{background:var(--sb-sel,#1f4a7a);color:#fff;border-color:#2d6aa8}
.xt-btn-tool.open{border-color:var(--sb-accent,#3b9cff)}
.xt-btn-tool:focus-visible{outline:2px solid var(--sb-accent,#3b9cff);outline-offset:1px}
.xt-btn-tool::after{content:attr(data-tip);position:absolute;left:calc(100% + 8px);top:50%;transform:translateY(-50%);white-space:nowrap;background:#0e1218;color:#dfe6ee;border:1px solid #2d3748;border-radius:4px;padding:3px 7px;font-size:11px;opacity:0;pointer-events:none;transition:opacity .12s;z-index:30}
.xt-btn-tool:hover::after,.xt-btn-tool:focus-visible::after{opacity:1}
.xt-drawer{position:absolute;left:${STRIP_W}px;top:0;bottom:0;width:${DRAWER_W}px;z-index:14;box-sizing:border-box;display:flex;flex-direction:column;background:rgba(20,24,32,.97);color:var(--sb-fg,#dfe6ee);
  border-right:1px solid var(--sb-line,#262d3a);box-shadow:4px 0 14px rgba(0,0,0,.35);font:12px/1.35 system-ui,-apple-system,'Segoe UI',sans-serif}
.xt-drawer *{box-sizing:border-box}
.xt-head{display:flex;align-items:center;gap:6px;padding:8px 10px;border-bottom:1px solid var(--sb-line,#262d3a);flex:0 0 auto}
.xt-title{flex:1 1 auto;font-weight:600;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.xt-close{width:22px;height:22px;padding:0;line-height:20px;text-align:center;background:transparent;color:inherit;border:1px solid var(--sb-line,#262d3a);border-radius:3px;cursor:pointer;font-size:14px}
.xt-close:hover{background:var(--sb-hover,#1c2230)}
.xt-body{flex:1 1 auto;min-height:0;overflow:auto;padding:8px 10px 12px;display:flex;flex-direction:column;gap:8px}
.xt-grip{position:absolute;right:-3px;top:0;bottom:0;width:6px;cursor:ew-resize}
.xt-grip:hover,.xt-grip.drag{background:rgba(59,156,255,.35)}
.xt-sec{color:var(--sb-dim,#8d99a8);text-transform:uppercase;font-size:10px;letter-spacing:.06em;font-weight:600;margin-top:2px}
.xt-note{color:var(--sb-dim,#8d99a8)}
.xt-status{color:#b9c4d2;font-variant-numeric:tabular-nums;min-height:16px}
.xt-row{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.xt-btn{background:#1b2230;color:inherit;border:1px solid #2d3748;border-radius:3px;padding:2px 9px;height:24px;cursor:pointer;font:inherit;white-space:nowrap}
.xt-btn:hover:not(:disabled){background:#243049;border-color:#3a4a66}
.xt-btn:disabled{opacity:.45;cursor:default}
.xt-btn.primary{background:#1f4a7a;border-color:#2d6aa8}
.xt-btn.primary:hover:not(:disabled){background:#26598f}
.xt-check{display:flex;align-items:center;gap:6px;cursor:pointer;user-select:none}
.xt-slider{display:grid;grid-template-columns:96px 1fr 52px;gap:6px;align-items:center}
.xt-slider input{width:100%;margin:0}
.xt-lbl{color:#b9c4d2}
.xt-val{text-align:right;font-variant-numeric:tabular-nums;color:var(--sb-dim,#8d99a8)}
.xt-select{display:grid;grid-template-columns:96px 1fr;gap:6px;align-items:center}
.xt-select select,.xt-num{background:#0e1218;color:inherit;border:1px solid var(--sb-line,#262d3a);border-radius:3px;height:24px;padding:0 4px;font:inherit;min-width:0}
.xt-chips{display:flex;flex-wrap:wrap;gap:4px}
.xt-chip{background:#10141b;color:#b9c4d2;border:1px solid #2d3748;border-radius:11px;padding:1px 9px;height:22px;cursor:pointer;font:inherit}
.xt-chip:hover{border-color:#3a4a66}
.xt-chip.on{background:#1f4a7a;border-color:#2d6aa8;color:#fff}
.xt-table-wrap{overflow:auto;border:1px solid var(--sb-line,#262d3a);border-radius:3px;max-height:46vh;min-height:60px}
.xt-table{border-collapse:collapse;width:100%;font-size:11px;font-variant-numeric:tabular-nums}
.xt-table th{position:sticky;top:0;background:#10141b;color:var(--sb-dim,#8d99a8);text-align:left;font-weight:600;padding:3px 5px;cursor:pointer;white-space:nowrap;user-select:none;z-index:1}
.xt-table th.sorted::after{content:' \\25B4'}
.xt-table th.sorted.desc::after{content:' \\25BE'}
.xt-table td{padding:2px 5px;white-space:nowrap;border-top:1px solid #1a202b;max-width:130px;overflow:hidden;text-overflow:ellipsis}
.xt-table tbody tr{cursor:pointer}
.xt-table tbody tr:hover{background:var(--sb-hover,#1c2230)}
.xt-table tbody tr.sel{background:var(--sb-sel,#1f4a7a)}
.xt-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px;vertical-align:baseline}
.xt-list{display:flex;flex-direction:column;gap:3px}
.xt-item{display:flex;align-items:center;gap:6px;padding:3px 6px;background:#10141b;border:1px solid var(--sb-line,#262d3a);border-radius:3px}
.xt-item .grow{flex:1 1 auto;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.xt-item .x{background:transparent;border:0;color:var(--sb-dim,#8d99a8);cursor:pointer;font-size:14px;line-height:1;padding:0 3px}
.xt-item .x:hover{color:#ff7a7a}
body.xt-on #xray-overlay{left:calc(var(--sb-w, 300px) + ${STRIP_W + 8}px) !important}
@keyframes xt-pulse{0%{r:6;opacity:1;stroke-width:3}100%{r:34;opacity:0;stroke-width:1}}
`;

export interface ToolbarHooks {
  /** A tool button was clicked. */
  click(tool: XrayTool): void;
  /** The drawer closed by itself (Escape, the close button). */
  closed(): void;
}

export class ToolbarView {
  readonly strip: HTMLElement;
  readonly drawer: HTMLElement;
  private readonly body: HTMLElement;
  private readonly titleEl: HTMLElement;
  private readonly grip: HTMLElement;
  private buttons = new Map<string, HTMLButtonElement>();
  private cleanup: (() => void) | null = null;
  private openId: string | null = null;
  private width = DRAWER_W;
  private userWidth: number | null = null;
  private escHandler: ((e: KeyboardEvent) => void) | null = null;

  constructor(private readonly stage: HTMLElement, private readonly app: ViewerApp, private readonly hooks: ToolbarHooks) {
    if (!document.getElementById('xray-toolbar-style')) {
      const st = document.createElement('style');
      st.id = 'xray-toolbar-style';
      st.textContent = CSS;
      document.head.appendChild(st);
    }
    this.strip = el('nav', 'xt-strip', { 'aria-label': 'Tools', id: 'xray-toolbar' });
    this.drawer = el('aside', 'xt-drawer hidden', { 'aria-label': 'Tool panel', id: 'xray-toolbar-drawer' });
    const head = el('div', 'xt-head');
    this.titleEl = el('div', 'xt-title');
    const close = el('button', 'xt-close', { type: 'button', 'aria-label': 'Close panel', title: 'Close (Esc)' }, '×');
    close.addEventListener('click', () => this.closeDrawer(true));
    head.append(this.titleEl, close);
    this.body = el('div', 'xt-body');
    this.grip = el('div', 'xt-grip', { role: 'separator', 'aria-orientation': 'vertical', title: 'Drag to resize' });
    this.drawer.append(head, this.body, this.grip);
    this.installResize();
    stage.append(this.strip, this.drawer);
    document.body.classList.add('xt-on');
  }

  get openToolId(): string | null {
    return this.openId;
  }

  get hidden(): boolean {
    return this.strip.classList.contains('hidden');
  }

  setHidden(h: boolean): void {
    this.strip.classList.toggle('hidden', h);
    document.body.classList.toggle('xt-on', !h);
    if (h) this.closeDrawer(true);
  }

  setTools(tools: readonly XrayTool[]): void {
    this.buttons.clear();
    this.strip.textContent = '';
    for (const t of tools) {
      const b = el('button', 'xt-btn-tool', { type: 'button', 'data-tool': t.id, 'aria-label': t.label, 'data-tip': `${t.label}: ${t.title}`, title: t.title });
      b.innerHTML = t.icon;
      b.addEventListener('click', () => this.hooks.click(t));
      this.strip.appendChild(b);
      this.buttons.set(t.id, b);
    }
    this.refresh(tools);
    if (this.openId && !this.buttons.has(this.openId)) this.closeDrawer(true);
  }

  /** Update active/open classes. */
  refresh(tools: readonly XrayTool[]): void {
    for (const t of tools) {
      const b = this.buttons.get(t.id);
      if (!b) continue;
      let active = false;
      try {
        active = !!t.isActive?.(this.app);
      } catch {
        active = false;
      }
      b.classList.toggle('active', active);
      b.setAttribute('aria-pressed', String(active));
      b.classList.toggle('open', this.openId === t.id);
    }
  }

  openDrawer(tool: XrayTool): void {
    this.closeDrawer(false);
    this.openId = tool.id;
    this.titleEl.textContent = tool.label;
    this.drawer.classList.remove('hidden');
    this.width = this.userWidth ?? tool.drawerWidth ?? DRAWER_W;
    this.applyWidth();
    this.body.textContent = '';
    try {
      const c = tool.panel?.(this.body, this.app);
      this.cleanup = typeof c === 'function' ? c : null;
    } catch (e) {
      this.body.appendChild(el('div', 'xt-note', undefined, `Could not open ${tool.label}: ${e instanceof Error ? e.message : String(e)}`));
      console.warn('[toolbar] panel failed', e);
    }
    // Escape closes the drawer: capture phase on the document, installed only while the drawer is open. The command
    // palette and other overlays get the key first; a tool that has its own pending state (measure) listens on window.
    this.escHandler = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return;
      if (getKeymap()?.anyOverlayOpen()) return;
      e.stopPropagation();
      e.preventDefault();
      this.closeDrawer(true);
    };
    document.addEventListener('keydown', this.escHandler, true);
    this.buttons.get(tool.id)?.classList.add('open');
  }

  closeDrawer(notify: boolean): void {
    if (this.escHandler) {
      document.removeEventListener('keydown', this.escHandler, true);
      this.escHandler = null;
    }
    const c = this.cleanup;
    this.cleanup = null;
    const was = this.openId;
    this.openId = null;
    try {
      c?.();
    } catch (e) {
      console.warn('[toolbar] panel cleanup failed', e);
    }
    this.body.textContent = '';
    this.drawer.classList.add('hidden');
    if (was) this.buttons.get(was)?.classList.remove('open');
    if (notify && was) this.hooks.closed();
  }

  private applyWidth(): void {
    this.width = clampDrawerWidth(this.width, this.stage.clientWidth || window.innerWidth);
    this.drawer.style.width = `${this.width}px`;
  }

  private installResize(): void {
    this.grip.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      this.grip.setPointerCapture(e.pointerId);
      this.grip.classList.add('drag');
      const startX = e.clientX;
      const startW = this.width;
      const move = (m: PointerEvent): void => {
        this.width = startW + (m.clientX - startX);
        this.userWidth = this.width;
        this.applyWidth();
      };
      const up = (): void => {
        this.grip.classList.remove('drag');
        this.grip.removeEventListener('pointermove', move);
        this.grip.removeEventListener('pointerup', up);
        this.grip.removeEventListener('pointercancel', up);
      };
      this.grip.addEventListener('pointermove', move);
      this.grip.addEventListener('pointerup', up);
      this.grip.addEventListener('pointercancel', up);
    });
  }
}
