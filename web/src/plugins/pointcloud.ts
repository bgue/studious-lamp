// Point cloud plugin: open scans (LAS, PLY, PCD, XYZ/PTS/TXT) and check them against the model (as-built deviation).
// Logic in src/pointcloud; this file wires the tool, lil-gui folder, palette actions, params section and window API.
//
//   window.__xrayPointCloud = { load, remove, computeDeviation, stats, ... }

import type { AppPlugin, ViewerApp } from '../app';
import { registerAction } from '../input/actions';
import { registerTool } from '../tools/registry';
import { registerParamSection } from '../ui/params';
import { COLOUR_MODES } from '../pointcloud/colour';
import { PointCloudController } from '../pointcloud/controller';
import type { PointCloudStats } from '../pointcloud/controller';
import type { DeviationStats } from '../pointcloud/deviation';
import { COORD_MODES, ICON, SCOPES, buildDrawer, buildGui, installDrop, pickPointCloud, pointCloudInput } from '../pointcloud/ui';

declare global {
  interface Window {
    __xrayPointCloud?: {
      /** Open a point cloud from a File, Blob or bytes; `name` decides the format when the bytes do not. */
      load(src: File | Blob | ArrayBuffer | Uint8Array, name?: string): Promise<PointCloudStats>;
      remove(): void;
      /** Measure the distance to the model for (a sample of) the points and colour them by band. */
      computeDeviation(): Promise<DeviationStats | null>;
      /** Match the cloud to the model (bounds centres, then 90 degree rotation search). */
      autoAlign(rotate?: boolean): { offset: [number, number, number]; rotationDeg: number; description: string } | null;
      readonly stats: PointCloudStats;
      readonly settings: PointCloudController['settings'];
      readonly status: string;
      readonly controller: PointCloudController;
    };
  }
}

let ctl: PointCloudController | null = null;

const obj = (v: unknown): Record<string, unknown> => (v && typeof v === 'object' ? (v as Record<string, unknown>) : {});

export const pointcloudPlugin: AppPlugin = {
  name: 'pointcloud',

  install(app: ViewerApp): void {
    const c = new PointCloudController(app);
    ctl = c;

    registerTool({
      id: 'pointcloud',
      label: 'Scan',
      title: 'Point cloud: open a scan and check it against the model (as-built deviation)',
      icon: ICON,
      order: 90,
      drawerWidth: 340,
      panel: (container, a) => buildDrawer(container, c, a),
    });

    const gui = app.panel;
    if (gui) buildGui(gui, c);

    registerParamSection('pointcloud', {
      collect: () => {
        const s = c.settings;
        return {
          visible: s.visible, pointSize: s.pointSize, sizeAttenuation: s.sizeAttenuation,
          colourBy: s.colourBy === 'deviation' ? 'rgb' : s.colourBy, budget: s.budget, coordinates: s.coordinates,
          offset: [s.offsetX, s.offsetY, s.offsetZ], rotationDeg: s.rotationDeg, tolerance: s.tolerance, scope: s.scope,
        };
      },
      apply: (value, bad, path) => {
        const o = obj(value);
        const s = c.settings;
        const num = (k: string, lo: number, hi: number, set: (v: number) => void): void => {
          if (o[k] === undefined) return;
          if (typeof o[k] === 'number' && Number.isFinite(o[k]) && (o[k] as number) >= lo && (o[k] as number) <= hi) set(o[k] as number);
          else bad.push(`${path}.${k}`);
        };
        if (o['visible'] !== undefined) {
          if (typeof o['visible'] === 'boolean') s.visible = o['visible'];
          else bad.push(`${path}.visible`);
        }
        if (o['sizeAttenuation'] !== undefined) {
          if (typeof o['sizeAttenuation'] === 'boolean') s.sizeAttenuation = o['sizeAttenuation'];
          else bad.push(`${path}.sizeAttenuation`);
        }
        num('pointSize', 1, 10, (v) => (s.pointSize = v));
        num('budget', 1000, 50_000_000, (v) => (s.budget = v));
        num('rotationDeg', -360, 360, (v) => (s.rotationDeg = v));
        num('tolerance', 0.0005, 5, (v) => (s.tolerance = v));
        const pick = (k: string, list: readonly string[], set: (v: string) => void): void => {
          if (o[k] === undefined) return;
          if (typeof o[k] === 'string' && list.includes(o[k] as string)) set(o[k] as string);
          else bad.push(`${path}.${k}`);
        };
        pick('colourBy', COLOUR_MODES, (v) => (s.colourBy = v as typeof s.colourBy));
        pick('coordinates', COORD_MODES, (v) => (s.coordinates = v as typeof s.coordinates));
        pick('scope', SCOPES, (v) => (s.scope = v as typeof s.scope));
        if (o['offset'] !== undefined) {
          const a = o['offset'];
          if (Array.isArray(a) && a.length === 3 && a.every((x) => typeof x === 'number' && Number.isFinite(x))) {
            s.offsetX = a[0] as number;
            s.offsetY = a[1] as number;
            s.offsetZ = a[2] as number;
          } else bad.push(`${path}.offset`);
        }
        if (c.loaded) {
          c.setCoordinates(s.coordinates);
          c.setAlignment();
          c.recolour();
        }
        c.applyDisplay();
        gui?.controllersRecursive().forEach((k) => k.updateDisplay());
      },
    });

    registerAction({ id: 'pointcloud.open', label: 'Point cloud: open file', group: 'Point cloud', keys: [], run: () => pickPointCloud(c) });
    registerAction({
      id: 'pointcloud.toggle', label: 'Point cloud: show / hide', group: 'Point cloud', keys: [],
      run: () => { c.settings.visible = !c.settings.visible; c.applyDisplay(); gui?.controllersRecursive().forEach((k) => k.updateDisplay()); },
    });
    registerAction({ id: 'pointcloud.deviation', label: 'Point cloud: compute deviation', group: 'Point cloud', keys: [], run: () => void c.computeDeviation() });

    installDrop(c);
    pointCloudInput(c); // the hidden picker input exists from the start (scripts and tests can feed it)

    window.__xrayPointCloud = {
      load: (src, name) => c.load(src, name),
      remove: () => c.remove(),
      computeDeviation: () => c.computeDeviation(),
      autoAlign: (rotate) => c.autoAlign(rotate ?? true),
      get stats() { return c.stats; },
      get settings() { return c.settings; },
      get status() { return c.status; },
      get controller() { return c; },
    };
  },

  onModel(): void {
    ctl?.setModelChanged();
  },

  onFrame(): void {
    ctl?.onFrame();
  },
};
