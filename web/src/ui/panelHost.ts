// Where a panel that is not a drawer sits (design 5.3). A panel is built once as an element and handed to a host, which decides where
// it goes: a tab of the right-hand sidebar (`rightSidebarPanelHost`), or the floating position when there is no sidebar. Nothing
// outside this file knows which one is in use.

import type { ViewerApp } from '../app';

export interface PanelHost {
  /** Put the element in its place. It starts hidden: call `show`. Mounting an id twice replaces the first element. */
  mount(id: string, title: string, el: HTMLElement): void;
  show(id: string): void;
  hide(id: string): void;
}

/**
 * The floating host: the element goes into the stage (the canvas parent) and is shown or hidden with the `hidden` attribute. The
 * element brings its own position (the review walk's `.xrw` styles: bottom left on a wide screen, a bottom sheet on a phone).
 */
export function floatingPanelHost(app: Pick<ViewerApp, 'canvas'>): PanelHost {
  const mounted = new Map<string, HTMLElement>();
  return {
    mount(id, title, el) {
      mounted.get(id)?.remove();
      el.setAttribute('aria-label', title);
      el.hidden = true;
      (app.canvas.parentElement ?? document.body).appendChild(el);
      mounted.set(id, el);
    },
    show(id) {
      const e = mounted.get(id);
      if (e) e.hidden = false;
    },
    hide(id) {
      const e = mounted.get(id);
      if (e) e.hidden = true;
    },
  };
}

// ---------------------------------------------------------------- the right-hand sidebar host
//
// A panel becomes a tab of the right sidebar (src/ui/rightSidebar.ts) while it is shown: `show` adds the tab (when needed) and opens the
// sidebar on it, `hide` takes the tab away so the sidebar falls back to its first tab. The element gets the `xrw-in` class, which turns
// the floating review-walk styles into a static column that fills the tab (on a phone the sidebar itself is the bottom sheet).

import type { RightTabHandle, RightTabSpec } from './rightSidebar';

export interface RightSidebarLike {
  addTab(spec: RightTabSpec): RightTabHandle;
}

export interface RightSidebarPanelOptions {
  /** Sort key of the tab (built-in tabs are 10, 20, 30). */
  order?: number;
  /** Preferred sidebar width while the tab is shown. */
  width?: number;
  /** Shorter tab label than the panel title. */
  label?: string;
}

/** A PanelHost over the right sidebar's `addTab`. Null when there is no sidebar, so the caller can fall back to the floating host. */
export function rightSidebarPanelHost(sidebar: RightSidebarLike | null | undefined, opts: RightSidebarPanelOptions = {}): PanelHost | null {
  if (!sidebar) return null;
  const panels = new Map<string, { title: string; el: HTMLElement; tab: RightTabHandle | null }>();
  return {
    mount(id, title, el) {
      const old = panels.get(id);
      old?.tab?.remove();
      old?.el.remove();
      el.setAttribute('aria-label', title);
      el.classList.add('xrw-in');
      el.hidden = true;
      panels.set(id, { title, el, tab: null });
    },
    show(id) {
      const p = panels.get(id);
      if (!p) return;
      p.el.hidden = false;
      p.tab ??= sidebar.addTab({
        id, label: opts.label ?? p.title, title: p.title, order: opts.order, width: opts.width,
        mount: (pane) => { pane.appendChild(p.el); return () => p.el.remove(); },
      });
      p.tab.show();
    },
    hide(id) {
      const p = panels.get(id);
      if (!p) return;
      p.el.hidden = true;
      p.tab?.remove();
      p.tab = null;
    },
  };
}
