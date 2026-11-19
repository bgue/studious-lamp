// Where a panel that is not a drawer sits (design 5.3). A panel is built once as an element and handed to a host, which decides where
// it goes: the floating position of the review walk today, the right-hand sidebar when that lands. Nothing outside this file knows
// which one is in use, so replacing the host is one change in one place (see `rightSidebarPanelHost` below).

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

// ---------------------------------------------------------------- adapter stub for the right-hand sidebar (not wired)
//
// The sidebar agent's API is expected to look like `rightSidebar.addTab({ id, label, mount })`, where `mount(host)` fills the tab body
// and the returned handle can show and hide the tab. This adapter turns it into a PanelHost. NOTHING CALLS IT YET.
// To wire the sidebar, make these two edits in src/plugins/revision.ts (the only place that picks a host):
//
//   import { rightSidebarPanelHost } from '../ui/panelHost';
//   const host: PanelHost = rightSidebarPanelHost(window.__xraySidebar!.right) ?? floatingPanelHost(app);
//
// (`window.__xraySidebar.right` is a placeholder for however the sidebar exposes `addTab`; change that one expression.)

export interface RightSidebarLike {
  addTab(spec: { id: string; label: string; mount: (body: HTMLElement) => void }): { show(): void; hide(): void } | null;
}

/** A PanelHost over `rightSidebar.addTab(...)`. Null when there is no sidebar, so the caller can fall back to the floating host. */
export function rightSidebarPanelHost(sidebar: RightSidebarLike | null | undefined): PanelHost | null {
  if (!sidebar) return null;
  const tabs = new Map<string, { show(): void; hide(): void } | null>();
  return {
    mount(id, title, el) {
      tabs.set(id, sidebar.addTab({ id, label: title, mount: (body) => { el.hidden = false; body.appendChild(el); } }));
    },
    show: (id) => tabs.get(id)?.show(),
    hide: (id) => tabs.get(id)?.hide(),
  };
}
