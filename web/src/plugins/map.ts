// Map plugin: an optional satellite or street map under the model (src/map). It wires the controller, the "Map" folder of the settings
// panel, the privacy notice, the attribution label and the manual aligner, and window.__xrayMap for scripts. OFF by default: no
// request is made until the person turns it on and accepts the notice. The map is in no params section, share link, saved view,
// preset or packed page. Logic in src/map. Docs: docs-features/map.md.

import type { AppPlugin, ViewerApp } from '../app';
import { AlignPanel } from '../map/align';
import { MapController } from '../map/controller';
import type { Georef, ManualLocation } from '../map/geo';
import type { MapSettings } from '../map/settings';
import { browserLocationStore } from '../map/store';
import { browserFetcher } from '../map/tiles';
import { AttributionLabel, buildMapFolder, showNotice } from '../map/ui';

declare global {
  interface Window {
    __xrayMap?: {
      readonly controller: MapController;
      /** Layer and location state: enabled, visible, zoom, tiles, the place, the status line, the attribution. */
      state(): ReturnType<MapController['state']>;
      /** The same as the switch in the panel; the notice is answered with `accept` (default: it is shown and waits). */
      setEnabled(on: boolean): Promise<boolean>;
      patch(p: Partial<MapSettings>): void;
      setManual(loc: ManualLocation | null, persist?: boolean): Promise<void>;
      openAlign(): void;
      readonly align: AlignPanel;
      /** The ground height (viewer y) and where the tiles are drawn. */
      georef(): Georef | null;
      /** Whether a ray from above meets anything of the map (it must not). */
      pickable(): boolean;
    };
  }
}

let ctl: MapController | null = null;
let attribution: AttributionLabel | null = null;
let alignPanel: AlignPanel | null = null;

export function mapController(): MapController | null {
  return ctl;
}

export const mapPlugin: AppPlugin = {
  name: 'map',

  install(app: ViewerApp): void {
    const r = app.renderer;
    ctl = new MapController({
      host: {
        scene: r.scene,
        camera: r.camera,
        viewportPx: () => Math.max(1, app.canvas.clientHeight * Math.min(window.devicePixelRatio || 1, 2)),
        markDirty: () => r.markDirty(),
        model: () => app.loaded?.model ?? null,
        modelName: () => app.modelName,
      },
      fetcher: browserFetcher(),
      store: browserLocationStore(),
      confirm: (text) => showNotice(text),
    });
    const stage = document.getElementById('stage') ?? app.canvas.parentElement ?? document.body;
    attribution = new AttributionLabel(stage);
    alignPanel = new AlignPanel(ctl, {
      canvas: app.canvas,
      camera: r.camera,
      setControlsEnabled: (on) => { r.controls.enabled = on; },
      topView: () => {
        const t = r.controls.target;
        const d = Math.max(5, r.camera.position.distanceTo(t));
        r.camera.position.set(t.x, t.y + d, t.z + 1e-3);
        r.controls.update();
        r.markDirty();
      },
      markDirty: () => r.markDirty(),
    }, stage);
    const a = alignPanel;
    const c = ctl;
    if (app.panel) {
      buildMapFolder(app.panel, c, () => {
        void (async () => {
          if (!c.settings.enabled) await c.setEnabled(true);
          a.open();
        })();
      });
    }
    window.__xrayMap = {
      controller: c,
      state: () => c.state(),
      setEnabled: (on) => c.setEnabled(on),
      patch: (p) => c.patch(p),
      setManual: (loc, persist) => c.setManual(loc, persist),
      openAlign: () => a.open(),
      align: a,
      georef: () => c.georef,
      pickable: () => c.layer.pickable,
    };
  },

  onModel(): void {
    void ctl?.onModel();
  },

  onFrame(_app: ViewerApp, now: number): boolean {
    if (!ctl) return false;
    const fading = ctl.tick(now);
    attribution?.set(ctl.attribution);
    return fading;
  },
};
