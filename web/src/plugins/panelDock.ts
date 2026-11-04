// Panel dock plugin: moves the lil-gui root (app.panel) out of its fixed top-right autoPlace position into
// the right-hand column #dock, which collapses to a 28 px rail like the left sidebar. `]` toggles it.
// See src/ui/panelDock.ts for the DOM and persistence ('xray.dock').

import type { AppPlugin, ViewerApp } from '../app';
import { PanelDock } from '../ui/panelDock';
import { MemoryStorage } from '../selectionSets';
import type { StorageLike } from '../selectionSets';

function storage(): StorageLike {
  try {
    const s = window.localStorage;
    s.getItem('xray.probe');
    return s;
  } catch {
    return new MemoryStorage();
  }
}

let dock: PanelDock | null = null;

function resizeRenderer(app: ViewerApp): void {
  app.renderer.resize();
  app.renderer.markDirty();
}

export const panelDockPlugin: AppPlugin = {
  name: 'panelDock',

  install(app) {
    const host = document.getElementById('dock');
    const panel = app.panel;
    if (!host || !panel) {
      console.warn('panelDock plugin: #dock or the lil-gui panel is missing; the panel keeps its floating position');
      return;
    }
    const narrow = window.matchMedia?.('(max-width: 700px)').matches ?? false;
    dock = new PanelDock(host, { storage: storage(), narrow, onResize: () => resizeRenderer(app) });
    dock.mount(panel.domElement);
    // The canvas fills #stage; whenever the stage changes size (toggle, window, mobile overlay) resize the renderer.
    if (typeof ResizeObserver !== 'undefined') new ResizeObserver(() => resizeRenderer(app)).observe(app.canvas);
    resizeRenderer(app);
  },
};

/** For scripts and the smoke test. */
export function getPanelDock(): PanelDock | null {
  return dock;
}
