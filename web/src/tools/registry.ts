// Tool registry for the viewer's action panel (the toolbar). Each feature plugin registers
// its tool in install(); the toolbar plugin (plugins/toolbar.ts) renders the registered tools,
// opens their drawers and remembers which are active. A packaged viewer (tools/xray-pack)
// can restrict the visible tools with window.__xrayBoot.tools (a list of tool ids).

import type { ViewerApp } from '../app';

export interface XrayTool {
  /**
   * Stable id. Reserved ids: 'open', 'presets', 'xray', 'viewModes', 'imaging', 'section',
   * 'measure', 'clearance', 'penetrations', 'bcf', 'pointcloud', 'xr', 'cleanup', 'largeModel'.
   */
  id: string;
  /** Short label shown under or beside the icon. */
  label: string;
  /** One-line description for the button tooltip. */
  title: string;
  /** Inline SVG markup for a 20x20 icon, using currentColor. */
  icon: string;
  /** Sort order within the toolbar (lower first). */
  order?: number;
  /** Optional drawer width in px (default 320); the user can still drag the drawer edge. */
  drawerWidth?: number;
  /** Optional: return false to hide the tool (feature unsupported here, such as WebXR). */
  available?(app: ViewerApp): boolean;
  /**
   * Optional drawer content. Called when the tool opens, with an empty container element in the
   * toolbar's drawer. Return a cleanup function, called when the drawer closes or another tool opens.
   */
  panel?(container: HTMLElement, app: ViewerApp): (() => void) | void;
  /** Optional on/off behaviour for mode-like tools (the toolbar shows the active state). */
  toggle?(app: ViewerApp, on: boolean): void;
  isActive?(app: ViewerApp): boolean;
}

const TOOLS = new Map<string, XrayTool>();
const listeners = new Set<() => void>();

export function registerTool(t: XrayTool): () => void {
  TOOLS.set(t.id, t);
  for (const l of listeners) l();
  return () => {
    if (TOOLS.get(t.id) === t) {
      TOOLS.delete(t.id);
      for (const l of listeners) l();
    }
  };
}

export function getTool(id: string): XrayTool | undefined {
  return TOOLS.get(id);
}

export function getTools(): XrayTool[] {
  return [...TOOLS.values()].sort((a, b) => (a.order ?? 100) - (b.order ?? 100) || a.id.localeCompare(b.id));
}

export function onToolsChanged(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

/** Boot configuration embedded by tools/xray-pack (absent in the normal viewer). */
export interface XrayBoot {
  /** Model name to open first (a key of window.__xrayEmbeddedModels). */
  model?: string;
  /** Page title. */
  title?: string;
  /** A params document (xray-params/1, partial allowed) applied after the model loads. */
  params?: unknown;
  /** A preset name or id applied after the model loads (before params). */
  preset?: string;
  /** Elements to select after load: GlobalIds, or 'class:IfcDuctSegment' entries. */
  select?: string[];
  /** Visible tool ids in the action panel, in order. Absent means all. */
  tools?: string[];
  /** Tool to open on start. */
  openTool?: string;
  /** Hide the right parameter dock and the left tree on start (a clean presentation page). */
  kiosk?: boolean;
  /** false: no top bar (visualisation modes and search). A kiosk page has none either. */
  topBar?: boolean;
  /** Saved views (an `xray-views/1` document or a list of views) added to the Views tab (src/plugins/views.ts). */
  views?: unknown;
  /** A saved view (name, id or 1-based position) opened at start, after everything else. */
  openView?: string;
}

declare global {
  interface Window {
    __xrayBoot?: XrayBoot;
  }
}

export function bootConfig(): XrayBoot {
  return (typeof window !== 'undefined' && window.__xrayBoot) || {};
}
