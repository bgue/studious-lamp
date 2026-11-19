// Right sidebar plugin: the tabbed column #dock that mirrors the left sidebar. Built-in tabs:
//   Properties      the selection's properties (moved here from the foot of the left sidebar; src/ui/propsView.ts)
//   Classification  the classify panel, the selected element's result and the review walk (src/plugins/classify.ts adds it)
//   Parameters      the lil-gui "X-ray parameters" panel (app.panel)
// Other features add tabs with `addRightSidebarTab` (see src/ui/rightSidebar.ts for the contract) or `window.__xrayRightSidebar`.
//
//   window.__xrayRightSidebar = { addTab, open(id), close(), toggle(), tabs(), state() }
//   action: panel.right (key ]). Persistence: localStorage `xray.dock`.
//
// Phone (max-width 700 px): the column is a bottom sheet with the same tabs, and the left sidebar and the sheet are never both
// open: opening one closes the other. The sheet is registered with the overlay (`ov.reserve`) so labels, markers, the gizmo and
// the drawing toolbar keep clear of it.

import type { AppPlugin, ViewerApp } from '../app';
import { MemoryStorage } from '../selectionSets';
import type { StorageLike } from '../selectionSets';
import { PropsView } from '../ui/propsView';
import type { PropsData } from '../ui/propsView';
import { RightSidebar, PHONE_QUERY, addRightSidebarTab, getRightSidebar, setRightSidebar } from '../ui/rightSidebar';
import type { RightTabHandle, RightTabSpec } from '../ui/rightSidebar';
import { getOverlay } from '../ui/overlay';
import { showToast } from '../ui/keymapView';
import { runQuery } from '../query';
import { collapseSidebar, openCriteriaSetEditor } from './sidebar';

export type { RightTabHandle, RightTabSpec } from '../ui/rightSidebar';
export { addRightSidebarTab, getRightSidebar } from '../ui/rightSidebar';

export interface RightSidebarApi {
  /** Add a tab (see src/ui/rightSidebar.ts). */
  addTab(spec: RightTabSpec): RightTabHandle;
  /** Open the sidebar on a tab. False for an unknown id. */
  open(id: string): boolean;
  close(): void;
  toggle(): boolean;
  /** Tab ids in order. */
  tabs(): string[];
  state(): { collapsed: boolean; tab: string; phone: boolean };
  /** The overlay's reserved rects in canvas pixels, including this sidebar's own (for scripts and the smoke test). */
  reserved(): Array<{ x: number; y: number; w: number; h: number }>;
}

declare global {
  interface Window {
    __xrayRightSidebar?: RightSidebarApi;
  }
}

const REFRESH_MS = 250;

function storage(): StorageLike {
  try {
    const s = window.localStorage;
    s.getItem('xray.probe');
    return s;
  } catch {
    return new MemoryStorage();
  }
}

function resizeRenderer(app: ViewerApp): void {
  app.renderer.resize();
  app.renderer.markDirty();
}

function propsData(app: ViewerApp): PropsData | null {
  const sel = app.selection;
  const id = sel[0];
  if (id === undefined) return null;
  const info = app.controller.describe(id);
  const e = app.controller.model.elements[id];
  if (!info || !e) return null;
  const storey = e.storey === null ? undefined : app.controller.model.storeys.find((s) => s.id === e.storey);
  return {
    globalId: e.globalId,
    ifcClass: info.ifcClass,
    name: info.name ?? '',
    storey: storey ? storey.name : 'No storey',
    storeyName: storey ? storey.name : null,
    material: e.material ?? '',
    bucket: info.bucket,
    proximityWeight: info.proximityWeight,
    occlusion: info.occlusion,
    targetAlpha: info.targetAlpha,
    alpha: info.alpha,
    more: sel.length - 1,
  };
}

let sidebar: RightSidebar | null = null;
let props: PropsView | null = null;
let lastRefresh = 0;
let appRef: ViewerApp | null = null;

function refreshProps(): void {
  const app = appRef;
  if (!props || !app || !app.loaded) return;
  if (!sidebar?.tabsVisible('properties')) return;
  props.update(propsData(app));
}

const phone = (): boolean => window.matchMedia?.(PHONE_QUERY).matches ?? false;

export const rightSidebarPlugin: AppPlugin = {
  name: 'rightSidebar',

  install(app) {
    const host = document.getElementById('dock');
    const panel = app.panel;
    if (!host) {
      console.warn('rightSidebar plugin: #dock not found in the page; the right sidebar is disabled');
      return;
    }
    appRef = app;
    const narrow = phone();
    const sb = new RightSidebar(host, { storage: storage(), narrow, onResize: () => resizeRenderer(app) });
    sidebar = sb;

    // ---- Properties
    sb.addTab({
      id: 'properties',
      label: 'Properties',
      order: 10,
      title: 'Properties of the selected element',
      helpKey: 'Right sidebar/Properties tab',
      mount(pane, ctx) {
        const v = new PropsView({
          selectWhere: (query, additive) => {
            const r = runQuery(app.controller.model, query);
            if (r.error) {
              showToast(r.error.message, 2500);
              return;
            }
            if (r.ids.length === 0) {
              showToast('No element matches');
              return;
            }
            app.selectIds(r.ids, additive);
            showToast(`${additive ? 'Added' : 'Selected'} ${r.ids.length} element${r.ids.length === 1 ? '' : 's'}`);
          },
          saveCriteria: (query, name) => openCriteriaSetEditor(query, name),
        });
        props = v;
        v.root.classList.add('props-in-dock');
        pane.append(v.root);
        ctx.onVisible((on) => {
          if (on) refreshProps();
        });
        refreshProps();
        return () => {
          props = null;
        };
      },
    });

    // ---- Parameters (the lil-gui panel). Moved in at once, not on first show: other plugins (help, search) find its controls in the DOM.
    if (panel) {
      const paramPane = sb.addTab({
        id: 'parameters',
        label: 'Parameters',
        order: 30,
        title: 'X-ray parameters (the lil-gui panel)',
        helpKey: 'Right sidebar/Parameters tab',
        mount() {
          /* the panel is moved into the pane below */
        },
      });
      void paramPane;
      const pane = sb.paneOf('parameters');
      const gui = panel.domElement;
      // lil-gui's own `autoPlace` positioning (fixed, top right) is removed; its title bar keeps working as an open/close of the list.
      gui.classList.remove('lil-auto-place', 'autoPlace');
      gui.style.removeProperty('position');
      pane?.append(gui);
    } else console.warn('rightSidebar plugin: the lil-gui panel is missing; there is no Parameters tab');

    setRightSidebar(sb); // adds the tabs that features registered before this point (Classification)

    // The canvas fills #stage; whenever the stage changes size (toggle, window, mobile sheet) resize the renderer.
    if (typeof ResizeObserver !== 'undefined') new ResizeObserver(() => resizeRenderer(app)).observe(app.canvas);

    // ---- phone: the left sidebar and the sheet are never both open
    const body = document.body;
    let prev = { sb: body.classList.contains('sb-collapsed'), dk: body.classList.contains('dk-collapsed') };
    if (narrow && !prev.sb && !prev.dk) sb.setCollapsed(true, false); // both stored as open on a wider screen: the sheet gives way, without forgetting the wide-screen choice
    prev = { sb: body.classList.contains('sb-collapsed'), dk: body.classList.contains('dk-collapsed') };
    new MutationObserver(() => {
      const now = { sb: body.classList.contains('sb-collapsed'), dk: body.classList.contains('dk-collapsed') };
      if (phone() && !now.sb && !now.dk) {
        if (prev.dk && !now.dk) collapseSidebar(); // the sheet just opened: close the left sidebar
        else if (prev.sb && !now.sb) sb.setCollapsed(true); // the left sidebar just opened: close the sheet
      }
      prev = now;
    }).observe(body, { attributes: true, attributeFilter: ['class'] });

    // ---- the overlay: the sheet covers the view on a phone (beside the canvas on a wide screen it covers nothing)
    getOverlay(app).reserve('right-sidebar', () => {
      if (sb.state.collapsed && !phone()) return null;
      const r = host.getBoundingClientRect();
      const c = app.canvas.getBoundingClientRect();
      const x0 = Math.max(r.left, c.left), y0 = Math.max(r.top, c.top), x1 = Math.min(r.right, c.right), y1 = Math.min(r.bottom, c.bottom);
      return x1 - x0 > 0 && y1 - y0 > 0 ? { x: x0 - c.left, y: y0 - c.top, w: x1 - x0, h: y1 - y0 } : null;
    });

    const api: RightSidebarApi = {
      addTab: (spec) => addRightSidebarTab(spec),
      open: (id) => sb.showTab(id),
      close: () => sb.setCollapsed(true),
      toggle: () => {
        sb.setCollapsed(!sb.state.collapsed);
        return !sb.state.collapsed;
      },
      tabs: () => sb.tabIds(),
      state: () => ({ collapsed: sb.state.collapsed, tab: sb.activeTab, phone: phone() }),
      reserved: () => getOverlay(app).reserved.map((r) => ({ x: r.x, y: r.y, w: r.w, h: r.h })),
    };
    window.__xrayRightSidebar = api;
    resizeRenderer(app);
  },

  onModel() {
    refreshProps();
  },

  onStatic() {
    lastRefresh = performance.now();
    refreshProps();
  },

  afterFrame(_app, now) {
    if (now - lastRefresh < REFRESH_MS) return;
    lastRefresh = now;
    refreshProps();
  },
};

/** For scripts and the smoke test. */
export function getPanelDock(): RightSidebar | null {
  return getRightSidebar() ?? sidebar;
}
