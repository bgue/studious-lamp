// Rendering plugin: order-independent transparency (weighted blended OIT, McGuire and Bavoil 2013) for the
// ghost pass. The renderer does the work (render/renderer.ts, render/oitMath.ts); this adds the "Rendering"
// folder: the toggle, the depth-weight choice and a status line about float colour buffers.
// Defaults: on when the context has float colour buffers, else off (the toggle is then disabled).
// `?oit=off` in the URL starts with it off; `window.__xray.renderer.setOit(bool)` switches it from scripts.

import type { AppPlugin, ViewerApp } from '../app';
import { OIT_WEIGHT_MODES } from '../render/oitMath';
import type { OitWeightMode } from '../render/oitMath';

interface RenderingParams {
  orderIndependent: boolean;
  depthWeight: OitWeightMode;
  status: string;
}

let params: RenderingParams | null = null;

export const oitPlugin: AppPlugin = {
  name: 'oit',
  /** Keep the toggle and status line honest if the renderer turned OIT off at runtime (incomplete framebuffer). */
  afterFrame(app: ViewerApp): void {
    const r = app.renderer;
    if (params && (params.status !== r.oitStatus || params.orderIndependent !== r.oitEnabled)) {
      params.status = r.oitStatus;
      params.orderIndependent = r.oitEnabled;
      app.panel?.folders.find((f) => f._title === 'Rendering')?.controllersRecursive().forEach((c) => c.updateDisplay());
    }
  },
  install(app: ViewerApp): void {
    const r = app.renderer;
    if (new URLSearchParams(location.search).get('oit') === 'off') r.setOit(false);
    const p: RenderingParams = {
      orderIndependent: r.oitEnabled,
      depthWeight: r.oitWeightMode,
      status: r.oitStatus,
    };
    params = p;
    const gui = app.panel;
    if (!gui) return;
    const folder = gui.addFolder('Rendering');
    const refresh = (): void => {
      p.orderIndependent = r.oitEnabled;
      p.status = r.oitStatus;
      folder.controllersRecursive().forEach((c) => c.updateDisplay());
    };
    const toggle = folder.add(p, 'orderIndependent').name('order-independent ghosts').onChange((v: boolean) => {
      r.setOit(v);
      r.markDirty();
      refresh();
    });
    const weight = folder.add(p, 'depthWeight', [...OIT_WEIGHT_MODES]).name('depth weight').onChange((v: OitWeightMode) => r.setOitWeight(v));
    folder.add(p, 'status').name('float buffers').disable().listen();
    if (!r.oitSupported) {
      toggle.disable();
      weight.disable();
    }
  },
};
