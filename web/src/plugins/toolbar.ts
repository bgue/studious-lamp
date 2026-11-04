// Toolbar plugin: the action panel (a 44 px icon strip at the left edge of #stage plus a drawer) for the tools that
// feature plugins register in src/tools/registry.ts. See docs-features/toolbar.md.
//
//   window.__xrayToolbar = { open(id), close(), toggle(), tools() }
//   actions: toolbar.toggle (key t), tool.<id> (no key; command palette)
//   window.__xrayBoot.tools / openTool (packaged viewers) decide which tools show and which one opens first.

import type { AppPlugin, ViewerApp } from '../app';
import { registerAction } from '../input/actions';
import { registerBuiltinTools } from '../tools/builtin';
import { bootConfig, getTool, getTools, onToolsChanged } from '../tools/registry';
import type { XrayTool } from '../tools/registry';
import { visibleTools } from '../tools/toolbarModel';
import { ToolbarView } from '../ui/toolbarView';

export interface ToolbarApi {
  /** Open a tool: its drawer if it has a panel, else switch it on. Returns false for an unknown or hidden id. */
  open(id: string): boolean;
  /** Close the drawer. */
  close(): void;
  /** Show or hide the whole strip (key t). Returns the new visibility. */
  toggle(): boolean;
  /** Ids of the tools the strip shows, in order. */
  tools(): string[];
}

declare global {
  interface Window {
    __xrayToolbar?: ToolbarApi;
  }
}

const STORE_KEY = 'xray.toolbar';

function readHidden(): boolean {
  try {
    const v = JSON.parse(window.localStorage.getItem(STORE_KEY) ?? 'null') as { hidden?: unknown } | null;
    return v?.hidden === true;
  } catch {
    return false;
  }
}

function saveHidden(hidden: boolean): void {
  try {
    window.localStorage.setItem(STORE_KEY, JSON.stringify({ hidden }));
  } catch {
    /* ignore */
  }
}

let view: ToolbarView | null = null;
let shown: XrayTool[] = [];
let appRef: ViewerApp | null = null;
let offActions: Array<() => void> = [];
let lastRefresh = 0;

function rebuild(): void {
  if (!view || !appRef) return;
  shown = visibleTools(getTools(), bootConfig(), appRef);
  view.setTools(shown);
  for (const off of offActions) off();
  offActions = shown.map((t) =>
    registerAction({
      id: `tool.${t.id}`,
      label: `Tool: ${t.label}`,
      group: 'Panels',
      keys: [],
      description: t.title,
      run: (app) => activate(app, t),
    }),
  );
}

/** What a click does: open or close the drawer for tools with a panel, else switch the tool on or off. */
function activate(app: ViewerApp, t: XrayTool): void {
  if (!view) return;
  if (t.panel) {
    if (view.openToolId === t.id) view.closeDrawer(true);
    else {
      if (view.hidden) setHidden(false);
      view.openDrawer(t);
    }
  } else if (t.toggle) {
    const on = t.isActive ? !t.isActive(app) : true;
    t.toggle(app, on);
  }
  view.refresh(shown);
}

function setHidden(h: boolean): void {
  view?.setHidden(h);
  saveHidden(h);
}

const api: ToolbarApi = {
  open(id) {
    const t = shown.find((x) => x.id === id) ?? (getTool(id) && visibleTools([getTool(id)!], bootConfig(), appRef ?? undefined).length > 0 ? getTool(id) : undefined);
    if (!t || !view || !appRef) return false;
    if (t.panel) {
      if (view.hidden) setHidden(false);
      if (view.openToolId !== t.id) view.openDrawer(t);
    } else if (t.toggle) {
      t.toggle(appRef, true);
    }
    view.refresh(shown);
    return true;
  },
  close() {
    view?.closeDrawer(true);
  },
  toggle() {
    if (!view) return false;
    setHidden(!view.hidden);
    return !view.hidden;
  },
  tools() {
    return shown.map((t) => t.id);
  },
};

export const toolbarPlugin: AppPlugin = {
  name: 'toolbar',

  install(app: ViewerApp): void {
    appRef = app;
    const stage = app.canvas.parentElement;
    if (!stage) return;
    registerBuiltinTools();
    view = new ToolbarView(stage, app, {
      click: (t) => activate(app, t),
      closed: () => view?.refresh(shown),
    });
    if (readHidden() && !bootConfig().tools) view.setHidden(true);
    onToolsChanged(rebuild);
    registerAction({
      id: 'toolbar.toggle',
      label: 'Show or hide the tool strip',
      group: 'Panels',
      keys: ['t'],
      description: 'Show or hide the action panel at the left edge of the canvas',
      run: () => void api.toggle(),
    });
    window.__xrayToolbar = api;
    rebuild();
  },

  onModel(app: ViewerApp): void {
    // available() can depend on the model; a first openTool from a packaged viewer runs from the boot plugin.
    rebuild();
    view?.refresh(shown);
    void app;
  },

  afterFrame(app: ViewerApp, now: number): void {
    // active states change from keys and the parameter panel: refresh a few times a second
    if (view && now - lastRefresh > 300) {
      lastRefresh = now;
      view.refresh(shown);
    }
    void app;
  },
};
