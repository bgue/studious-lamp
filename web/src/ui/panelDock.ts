// Right-hand dock for the lil-gui parameter panel. Pure DOM, no app dependency: the plugin
// (plugins/panelDock.ts) hands it the #dock element and the lil-gui root element.
//
// Layout lives in index.html (#app > #sidebar | #stage | #dock). Collapsed state is persisted in
// localStorage under `xray.dock` ({ collapsed: boolean }) and mirrored on <body> as `dk-collapsed`
// (index.html applies it before first paint, like `sb-collapsed` for the left sidebar).

import { el } from './dom';
import { registerAction } from '../input/actions';

export const DOCK_KEY = 'xray.dock';
export const DOCK_TRANSITION_MS = 220;

export interface DockState {
  collapsed: boolean;
}

export interface DockStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

/** Parse the stored state; `narrow` (viewport <= 700 px) is the default for "collapsed" when nothing valid is stored. */
export function parseDockState(raw: string | null, narrow: boolean): DockState {
  try {
    const v = JSON.parse(raw ?? 'null') as Partial<DockState> | null;
    if (v && typeof v.collapsed === 'boolean') return { collapsed: v.collapsed };
  } catch {
    /* corrupt: fall through to the default */
  }
  return { collapsed: narrow };
}

export interface DockOptions {
  /** Called after the layout changed (immediately, and once more when the width transition has ended). */
  onResize?: () => void;
  storage?: DockStorage | null;
  narrow?: boolean;
}

export class PanelDock {
  readonly host: HTMLElement;
  readonly toggle: HTMLButtonElement;
  readonly body: HTMLElement;
  readonly railLabel: HTMLElement;
  state: DockState;

  private readonly store: DockStorage | null;
  private readonly onResize: () => void;

  constructor(host: HTMLElement, opts: DockOptions = {}) {
    this.host = host;
    this.store = opts.storage ?? null;
    this.onResize = opts.onResize ?? (() => undefined);
    let raw: string | null = null;
    try {
      raw = this.store?.getItem(DOCK_KEY) ?? null;
    } catch {
      raw = null;
    }
    this.state = parseDockState(raw, opts.narrow ?? false);

    host.textContent = '';
    const top = el('div', 'dk-top');
    this.toggle = el('button', 'dk-toggle', { type: 'button', 'aria-controls': 'dk-body' });
    const title = el('span', 'dk-title', {}, 'X-ray parameters');
    top.append(this.toggle, title);
    this.railLabel = el('div', 'dk-rail-label', {}, 'X-ray parameters');
    this.body = el('div', 'dk-body', { id: 'dk-body' });
    host.append(top, this.railLabel, this.body);

    this.toggle.addEventListener('click', () => this.setCollapsed(!this.state.collapsed));
    this.railLabel.addEventListener('click', () => this.setCollapsed(false));
    host.addEventListener('transitionend', (e) => {
      if (e.propertyName === 'width') this.onResize();
    });
    // `]` toggles the dock through the action registry (keymap plugin owns the key).
    registerAction({
      id: 'panel.right',
      label: 'Toggle parameter panel',
      group: 'Panels',
      keys: [']'],
      run: () => this.setCollapsed(!this.state.collapsed),
    });
    this.apply();
  }

  /**
   * Move a lil-gui root into the dock. lil-gui's own `autoPlace` positioning (fixed, top right) is removed;
   * its title bar keeps working as a plain open/close of the parameter list.
   */
  mount(guiRoot: HTMLElement): void {
    guiRoot.classList.remove('lil-auto-place', 'autoPlace');
    guiRoot.style.removeProperty('position');
    this.body.appendChild(guiRoot);
  }

  setCollapsed(collapsed: boolean): void {
    this.state.collapsed = collapsed;
    this.apply();
    try {
      this.store?.setItem(DOCK_KEY, JSON.stringify(this.state));
    } catch {
      /* ignore */
    }
    // The canvas resizes with the stage (ResizeObserver); this also covers the end of the width transition.
    this.onResize();
    window.setTimeout(this.onResize, DOCK_TRANSITION_MS);
  }

  private apply(): void {
    const c = this.state.collapsed;
    document.body.classList.toggle('dk-collapsed', c);
    this.toggle.setAttribute('aria-expanded', String(!c));
    this.toggle.title = c ? 'Expand parameter panel (])' : 'Collapse parameter panel (])';
    this.toggle.textContent = c ? '‹' : '›';
  }
}
