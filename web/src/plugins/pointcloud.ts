// Point cloud plugin: open scans (LAS, PLY, PCD, XYZ/PTS/TXT) and check them against the model (as-built deviation).
// Logic in src/pointcloud; this file wires the tool, lil-gui folder, palette actions, params section and window API.
//
//   window.__xrayPointCloud = { load, remove, computeDeviation, stats, ... }

import type { AppPlugin, ViewerApp } from '../app';
import { registerAction } from '../input/actions';
import { registerTool } from '../tools/registry';
import { registerParamSection } from '../ui/params';
import { PointCloudController } from '../pointcloud/controller';
import type { PointCloudStats } from '../pointcloud/controller';
import type { DeviationStats } from '../pointcloud/deviation';
import type { IcpResult } from '../pointcloud/icp';
import { PairTool } from '../pointcloud/pairs';
import { applyPointCloudParams, collectPointCloudParams } from '../pointcloud/params';
import type { Mat4, PairSolution } from '../pointcloud/register';
import { ICON, buildDrawer, buildGui, installDrop, pickPointCloud, pointCloudInput } from '../pointcloud/ui';

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
      /** Total transform, cloud frame (axis mapped, before alignment) -> viewer, column-major 4x4. */
      readonly matrix: Mat4;
      /** Set the total transform (pushes the previous one on the undo stack). */
      setMatrix(m: Mat4, description?: string): void;
      undoAlignment(): boolean;
      resetAlignment(): void;
      /** 3-point alignment: start, pick at client positions (cloud, model, cloud, ...), read the solution, apply. */
      pairs: {
        start(): boolean;
        clickAt(clientX: number, clientY: number): 'cloud' | 'model' | null;
        addCloud(c: [number, number, number]): void;
        addModel(v: [number, number, number]): void;
        undo(): void;
        cancel(): void;
        apply(): boolean;
        readonly solution: PairSolution | null;
        readonly step: 'cloud' | 'model';
        readonly active: boolean;
      };
      /** Point-to-plane ICP against the model; applies the result when it improved the fit. */
      /** `normals: false` matches without normal compatibility (as before the oriented normals). */
      refine(opts?: { samples?: number; maxIterations?: number; startDistance?: number; trim?: number; minDistance?: number; normals?: boolean }): Promise<IcpResult | null>;
      /** Shown cloud point under a client position. */
      pickCloudAt(clientX: number, clientY: number): { index: number; cloud: [number, number, number]; world: [number, number, number] } | null;
      readonly stats: PointCloudStats;
      readonly settings: PointCloudController['settings'];
      readonly status: string;
      readonly controller: PointCloudController;
    };
  }
}

let ctl: PointCloudController | null = null;

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
      collect: () => collectPointCloudParams(c.settings),
      apply: (value, bad, path) => {
        const s = c.settings;
        applyPointCloudParams(s, value, bad, path);
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
    registerAction({
      id: 'pointcloud.align3', label: 'Point cloud: align by 3 points', group: 'Point cloud', keys: [],
      run: () => { window.__xrayToolbar?.open('pointcloud'); if (!c.pairMode) c.startPairs(); },
    });
    registerAction({ id: 'pointcloud.refine', label: 'Point cloud: refine alignment (ICP)', group: 'Point cloud', keys: [], run: () => void c.refine() });

    const pairTool = new PairTool(app, c);

    installDrop(c);
    pointCloudInput(c); // the hidden picker input exists from the start (scripts and tests can feed it)

    window.__xrayPointCloud = {
      load: (src, name) => c.load(src, name),
      remove: () => c.remove(),
      computeDeviation: () => c.computeDeviation(),
      autoAlign: (rotate) => c.autoAlign(rotate ?? true),
      get matrix() { return c.totalMatrix; },
      setMatrix: (m, description) => c.applyTotal(m, description ?? 'Set by script.'),
      undoAlignment: () => c.undoAlignment(),
      resetAlignment: () => c.resetAlignment(),
      pairs: {
        start: () => c.startPairs(),
        clickAt: (x, y) => pairTool.clickAt(x, y),
        addCloud: (p) => c.addCloudPoint(p),
        addModel: (p) => c.addModelPoint(p),
        undo: () => c.undoPair(),
        cancel: () => c.cancelPairs(),
        apply: () => c.applyPairs(),
        get solution() { return c.pairSolution; },
        get step() { return c.pairStep; },
        get active() { return c.pairMode; },
      },
      refine: (opts) => c.refine(opts),
      pickCloudAt: (x, y) => c.pickCloudAt(x, y),
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
