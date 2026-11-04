// WebXR plugin (experimental): enter VR or AR from a button, an action or the tool drawer. The session logic is in
// src/xr/session.ts and the maths in src/xr/maths.ts; this file owns the lil-gui folder `WebXR`, the tool, the actions, the
// params section and the window API. See docs-features/webxr.md.
//
//   window.__xrayXr = { enter(mode), exit(), state(), setArScale(s), config, manager }
//
// Feature detection: navigator.xr and isSessionSupported('immersive-vr') / ('immersive-ar'). When neither is supported the
// tool, the folder and the buttons stay hidden.

import type { AppPlugin, ViewerApp } from '../app';
import { registerAction } from '../input/actions';
import { registerTool } from '../tools/registry';
import type { XrayTool } from '../tools/registry';
import { button, check, select, statusLine } from '../tools/ui';
import type { Widget } from '../tools/ui';
import { registerParamSection } from '../ui/params';
import { AR_SCALES } from '../xr/maths';
import type { ArScale } from '../xr/maths';
import { XrManager } from '../xr/session';
import type { XrMode, XrState } from '../xr/session';

export interface XrApi {
  /** Start a session (call from a user gesture, as the browser requires). */
  enter(mode: XrMode): Promise<void>;
  exit(): void;
  state(): XrState;
  setArScale(s: ArScale): void;
  readonly config: XrManager['config'];
  readonly manager: XrManager | null;
}

declare global {
  interface Window {
    __xrayXr?: XrApi;
  }
}

let mgr: XrManager | null = null;

const api: XrApi = {
  enter: (m) => (mgr ? mgr.enter(m) : Promise.resolve()),
  exit: () => mgr?.exit(),
  state: () => mgr!.state(),
  setArScale: (s) => mgr?.setArScale(s),
  get config() {
    return mgr!.config;
  },
  get manager() {
    return mgr;
  },
};

const ICON =
  '<svg viewBox="0 0 20 20" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M2.5 7.5a2 2 0 0 1 2-2h11a2 2 0 0 1 2 2v4a2 2 0 0 1-2 2h-3l-1.2-1.8a1.6 1.6 0 0 0-2.6 0L7.5 13.5h-3a2 2 0 0 1-2-2z"/>' +
  '<circle cx="6.8" cy="9.5" r="0.9"/><circle cx="13.2" cy="9.5" r="0.9"/></svg>';

function drawer(box: HTMLElement): (() => void) | void {
  const m = mgr;
  if (!m) return;
  const widgets: Widget[] = [];
  const add = (w: Widget): void => {
    widgets.push(w);
    box.appendChild(w.root);
    w.update();
  };
  const vr = button('Enter VR', () => void m.enter('vr'), { primary: true, title: 'Start a virtual reality session at real scale' });
  const ar = button('Enter AR', () => void m.enter('ar'), { primary: true, title: 'Start an augmented reality session and place the model' });
  box.append(vr, ar);
  add(select('AR scale', AR_SCALES, () => m.config.arScale, (v) => m.setArScale(v)));
  add(check('pointer rays', () => m.config.pointerRays, (v) => (m.config.pointerRays = v)));
  const leave = button('Leave XR session', () => m.exit(), { title: 'End the running session' });
  box.appendChild(leave);
  const st = statusLine('');
  box.appendChild(st);
  const upd = (): void => {
    widgets.forEach((w) => w.update());
    vr.setDisabled(m.support.vr ? (m.active ? 'A session is running' : false) : 'Virtual reality is not supported on this device');
    ar.setDisabled(m.support.ar ? (m.active ? 'A session is running' : false) : 'Augmented reality is not supported on this device');
    leave.setDisabled(m.active ? false : 'No session is running');
    st.set(m.status);
  };
  const off = m.onChange(upd);
  upd();
  return off;
}

export const xrPlugin: AppPlugin = {
  name: 'xr',

  install(app: ViewerApp): void {
    const m = new XrManager(app);
    mgr = m;
    window.__xrayXr = api;

    registerAction({
      id: 'xr.vr',
      label: 'WebXR: enter VR (experimental)',
      group: 'Modes',
      keys: [],
      description: 'Start an immersive virtual reality session at real scale',
      enabled: () => m.support.vr && !m.active,
      run: () => void m.enter('vr'),
    });
    registerAction({
      id: 'xr.ar',
      label: 'WebXR: enter AR (experimental)',
      group: 'Modes',
      keys: [],
      description: 'Start an augmented reality session and place the model',
      enabled: () => m.support.ar && !m.active,
      run: () => void m.enter('ar'),
    });

    const tool: XrayTool = {
      id: 'xr',
      label: 'WebXR',
      title: 'WebXR (experimental): look at the model in VR or place it in AR',
      icon: ICON,
      order: 95,
      drawerWidth: 320,
      available: () => m.support.vr || m.support.ar,
      panel: (box) => drawer(box),
      isActive: () => m.active,
    };
    registerTool(tool);

    registerParamSection('xr', {
      collect: () => ({ scale: m.config.arScale, pointerRays: m.config.pointerRays }),
      apply(value, bad, path) {
        if (value === null || typeof value !== 'object') {
          bad.push(path);
          return;
        }
        const o = value as Record<string, unknown>;
        for (const k of Object.keys(o)) {
          if (k === 'scale' && typeof o[k] === 'string' && (AR_SCALES as readonly string[]).includes(o[k] as string)) m.setArScale(o[k] as ArScale);
          else if (k === 'pointerRays' && typeof o[k] === 'boolean') m.config.pointerRays = o[k] as boolean;
          else bad.push(`${path}.${k}`);
        }
        refresh();
      },
    });

    // The folder stays hidden until the device is checked (and for good when neither VR nor AR is supported).
    const gui = app.panel;
    let controllers: Array<{ updateDisplay(): unknown }> = [];
    let refresh = (): void => controllers.forEach((c) => c.updateDisplay());
    if (gui) {
      const folder = gui.addFolder('WebXR');
      folder.close();
      folder.hide();
      const actions = { enterVr: () => void m.enter('vr'), enterAr: () => void m.enter('ar') };
      const cVr = folder.add(actions, 'enterVr').name('Enter VR');
      const cAr = folder.add(actions, 'enterAr').name('Enter AR');
      const cScale = folder.add(m.config, 'arScale', [...AR_SCALES]).name('AR scale').onChange((v: ArScale) => m.setArScale(v));
      const view = { status: m.status };
      const cStatus = folder.add(view, 'status').name('XR status').disable();
      const cRays = folder.add(m.config, 'pointerRays').name('pointer rays');
      controllers = [cScale, cStatus, cRays];
      refresh = (): void => {
        view.status = m.status;
        controllers.forEach((c) => c.updateDisplay());
      };
      const sync = (): void => {
        const { vr, ar } = m.support;
        if (vr || ar) folder.show();
        else folder.hide();
        if (vr) cVr.show();
        else cVr.hide();
        if (ar) cAr.show();
        else cAr.hide();
        refresh();
      };
      m.onChange(sync);
    }

    // Check the device, then show the tool (re-registering tells the toolbar to look at available() again).
    void m.detect().then(() => registerTool(tool));
  },

  beforeFrame(_app: ViewerApp, now: number, dt: number): void {
    mgr?.beforeFrame(now, dt);
  },
};
