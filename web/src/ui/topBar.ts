// Top bar: a thin strip (32 px) along the top of #stage. On the left a segmented control with four visualisation modes,
// then a host element (#xray-topbar-search) that takes the rest of the width for the search bar (src/plugins/awesomeBar.ts
// mounts into it; this module leaves it empty). Docs: docs-features/topbar.md.
//
// A mode is a thin wrapper: it applies a built-in preset (src/presets/builtin.ts) through window.__xrayPresets, so modes,
// presets, saved views and share links stay one thing. The pure part (MODES, modeForPreset, clickPlan, barVisible) has no
// DOM and is tested in node; TopBarView is the DOM.

export const TOPBAR_H = 32;
export const SEARCH_HOST_ID = 'xray-topbar-search';
export const TOPBAR_ID = 'xray-topbar';

export type ModeId = 'ghost' | 'radiograph' | 'glow' | 'cutaway';

export interface ModeDef {
  id: ModeId;
  label: string;
  /** The built-in preset the mode applies. */
  presetId: string;
  /** Default key chord of the action `topbar.mode.<id>`. */
  key: string;
  /** Key name for tooltips and docs. */
  keyLabel: string;
  icon: string;
}

const svg = (body: string): string =>
  `<svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;

export const MODES: readonly ModeDef[] = [
  {
    id: 'ghost',
    label: 'Ghost',
    presetId: 'coordination',
    key: 'Shift+code:Digit1',
    keyLabel: 'Shift+1',
    icon: svg('<path d="M5 17V9a5 5 0 0 1 10 0v8l-2.5-2-2.5 2-2.5-2z"/><circle cx="8.2" cy="9" r=".6" fill="currentColor"/><circle cx="11.8" cy="9" r=".6" fill="currentColor"/>'),
  },
  {
    id: 'radiograph',
    label: 'Radiograph',
    presetId: 'radiograph',
    key: 'Shift+code:Digit2',
    keyLabel: 'Shift+2',
    icon: svg('<rect x="3" y="3" width="14" height="14" rx="2"/><path d="M8 6.5v7M12 6.5v7M6.5 8.5h7M6.5 11.5h7" stroke-width="1.3"/>'),
  },
  {
    id: 'glow',
    label: 'Glow',
    presetId: 'focus-glow',
    key: 'Shift+code:Digit3',
    keyLabel: 'Shift+3',
    icon: svg('<circle cx="10" cy="10" r="3"/><path d="M10 2.5v2.2M10 15.3v2.2M2.5 10h2.2M15.3 10h2.2M4.7 4.7l1.6 1.6M13.7 13.7l1.6 1.6M15.3 4.7l-1.6 1.6M6.3 13.7l-1.6 1.6"/>'),
  },
  {
    id: 'cutaway',
    label: 'Cutaway',
    presetId: 'peel-only',
    key: 'Shift+code:Digit4',
    keyLabel: 'Shift+4',
    icon: svg('<path d="M3 6.5 10 3l7 3.5v7L10 17l-7-3.5z"/><path d="M10 10V3M10 10l7-3.5M10 10l-7-3.5" stroke-width="1.2"/><path d="M10 10v7" stroke-dasharray="1.6 1.8" stroke-width="1.2"/>'),
  },
];

/** The preset id that goes with a click on the active mode: normal shaded view (X-ray off, the modes' sections reset). */
export const OFF_PRESET_ID = 'plain';

export function modeById(id: string): ModeDef | undefined {
  return MODES.find((m) => m.id === id);
}

export function presetForMode(id: ModeId): string {
  return modeById(id)!.presetId;
}

/** The mode that goes with the active preset id (null: no preset is active, a setting changed since, or another preset). */
export function modeForPreset(presetId: string | null | undefined): ModeId | null {
  if (!presetId) return null;
  return MODES.find((m) => m.presetId === presetId)?.id ?? null;
}

export type ClickPlan = { kind: 'apply'; presetId: string } | { kind: 'off'; presetId: string };

/** What a click on `clicked` does when `active` is the highlighted mode: the active mode again returns to normal view. */
export function clickPlan(active: ModeId | null, clicked: ModeId): ClickPlan {
  if (active === clicked) return { kind: 'off', presetId: OFF_PRESET_ID };
  return { kind: 'apply', presetId: presetForMode(clicked) };
}

export interface BarVisibilityInput {
  /** params `topBar.visible`. */
  visible: boolean;
  /** Packaged page with --kiosk. */
  kiosk: boolean;
  /** A WebXR session is running. */
  xr: boolean;
  /** Packaged page with --no-topbar. */
  disabledByBoot?: boolean;
}

export function barVisible(i: BarVisibilityInput): boolean {
  return i.visible && !i.kiosk && !i.xr && !i.disabledByBoot;
}

// ---------------------------------------------------------------- DOM

const CSS = `
:root{--tb-h:0px}
#${TOPBAR_ID}{position:absolute;left:0;right:0;top:0;height:${TOPBAR_H}px;z-index:16;box-sizing:border-box;display:flex;align-items:center;gap:8px;padding:0 8px;
  background:var(--sb-bg,#141820);color:var(--sb-fg,#dfe6ee);border-bottom:1px solid var(--sb-line,#262d3a);
  font:12px/1 system-ui,-apple-system,'Segoe UI',sans-serif;user-select:none;-webkit-user-select:none}
#${TOPBAR_ID}[hidden]{display:none}
#${TOPBAR_ID} *{box-sizing:border-box}
#${TOPBAR_ID} .tb-modes{flex:0 0 auto;display:flex;align-items:stretch;height:24px;border:1px solid #2d3748;border-radius:5px;overflow:hidden}
#${TOPBAR_ID} .tb-mode{display:flex;align-items:center;gap:5px;height:100%;padding:0 10px;margin:0;background:#1b2230;color:#b9c4d2;border:0;border-left:1px solid #2d3748;
  font:inherit;cursor:pointer;white-space:nowrap}
#${TOPBAR_ID} .tb-mode:first-child{border-left:0}
#${TOPBAR_ID} .tb-mode:hover{background:#243049;color:#fff}
#${TOPBAR_ID} .tb-mode[aria-pressed=true]{background:var(--sb-sel,#1f4a7a);color:#fff;box-shadow:inset 0 -2px 0 var(--sb-accent,#3b9cff)}
#${TOPBAR_ID} .tb-mode:focus-visible{outline:2px solid var(--sb-accent,#3b9cff);outline-offset:-2px}
#${TOPBAR_ID} .tb-mode svg{flex:0 0 auto}
#${SEARCH_HOST_ID}{flex:1 1 auto;min-width:0;height:100%;display:flex;align-items:center;position:relative}
@media (max-width:700px){
  #${TOPBAR_ID}{gap:6px;padding:0 6px}
  #${TOPBAR_ID} .tb-mode{padding:0;width:30px;justify-content:center}
  #${TOPBAR_ID} .tb-label{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
  #${SEARCH_HOST_ID}{min-width:60px}
}
@media (max-width:700px){
  body.tb-on #sidebar,body.tb-on #dock{top:var(--tb-h,0px)}
}
.xt-strip,.xt-drawer{top:var(--tb-h,0px)!important}
`;

export interface TopBarHandlers {
  /** A mode button was clicked. */
  click(id: ModeId): void;
}

export class TopBarView {
  readonly root: HTMLDivElement;
  readonly searchHost: HTMLDivElement;
  private readonly buttons = new Map<ModeId, HTMLButtonElement>();
  private shown = true;

  constructor(parent: HTMLElement, handlers: TopBarHandlers) {
    if (!document.getElementById('xray-topbar-css')) {
      const style = document.createElement('style');
      style.id = 'xray-topbar-css';
      style.textContent = CSS;
      document.head.appendChild(style);
    }
    const root = document.createElement('div');
    root.id = TOPBAR_ID;
    root.setAttribute('role', 'toolbar');
    root.setAttribute('aria-label', 'Visualisation modes and search');
    const group = document.createElement('div');
    group.className = 'tb-modes';
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', 'Visualisation mode');
    for (const m of MODES) {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'tb-mode';
      b.dataset['mode'] = m.id;
      b.setAttribute('aria-pressed', 'false');
      b.setAttribute('aria-label', `${m.label} (${m.keyLabel})`);
      b.setAttribute('data-help-key', `Top bar/${m.label}`);
      b.setAttribute('data-help-title', m.label);
      b.innerHTML = `${m.icon}<span class="tb-label">${m.label}</span>`;
      b.addEventListener('click', () => handlers.click(m.id));
      group.appendChild(b);
      this.buttons.set(m.id, b);
    }
    const host = document.createElement('div');
    host.id = SEARCH_HOST_ID;
    root.append(group, host);
    parent.appendChild(root);
    this.root = root;
    this.searchHost = host;
  }

  /** Highlight a mode (null: none). */
  setActive(id: ModeId | null): void {
    for (const [mid, b] of this.buttons) {
      const on = mid === id;
      if (b.getAttribute('aria-pressed') !== String(on)) b.setAttribute('aria-pressed', String(on));
    }
  }

  get activeMode(): ModeId | null {
    for (const [mid, b] of this.buttons) if (b.getAttribute('aria-pressed') === 'true') return mid;
    return null;
  }

  get visible(): boolean {
    return this.shown;
  }

  /** Show or hide the bar; the body class and `--tb-h` tell the strip, the drawers and the phone rails where to start. */
  setVisible(v: boolean): void {
    this.shown = v;
    this.root.hidden = !v;
    document.body.classList.toggle('tb-on', v);
    document.body.style.setProperty('--tb-h', v ? `${TOPBAR_H}px` : '0px');
  }
}
