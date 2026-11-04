// Toolbar wrappers for features that already live elsewhere: open a model, x-ray, view modes and cleanup.
// They talk to those features through their public hooks (window.__xrayViewModes, window.__xrayCleanup, the
// "Open model" panel), so they stay thin.

import type { ViewerApp } from '../app';
import { defaultRules } from '../cleanup/analysis';
import type { CleanupRules } from '../cleanup/analysis';
import { FRONT_TREATMENTS } from '../viewModes/maths';
import type { FrontTreatment } from '../viewModes/maths';
import { ICONS } from './icons';
import { registerTool } from './registry';
import { button, check, note, row, section, select, slider, statusLine } from './ui';
import type { Widget } from './ui';

function openModel(app: ViewerApp): void {
  const ctl = app.panel?.controllersRecursive().find((c) => c.property === 'open' && typeof (c.object as { open?: unknown }).open === 'function');
  if (ctl) {
    (ctl.object as { open: () => void }).open();
    return;
  }
  (document.getElementById('xray-open-file-input') as HTMLInputElement | null)?.click();
}

function viewModesPanel(box: HTMLElement): (() => void) | void {
  const api = window.__xrayViewModes;
  if (!api) {
    box.appendChild(note('The view modes feature is not available in this build.'));
    return;
  }
  const c = api.config;
  const widgets: Widget[] = [];
  const add = (w: Widget): void => {
    widgets.push(w);
    box.appendChild(w.root);
    w.update();
  };
  box.appendChild(section('Behind only'));
  add(check('Behind-only view (B)', () => c.behind.enabled, (v) => api.setBehind({ enabled: v })));
  add(select<FrontTreatment>('front treatment', FRONT_TREATMENTS, () => c.behind.frontTreatment, (v) => api.setBehind({ frontTreatment: v })));
  add(slider('offset (m)', -2, 3, 0.01, () => c.behind.offset, (v) => api.setBehind({ offset: v }), (v) => v.toFixed(2)));
  add(slider('front alpha', 0, 1, 0.01, () => c.behind.frontAlpha, (v) => api.setBehind({ frontAlpha: v }), (v) => v.toFixed(2)));
  box.appendChild(section('Partial peelback'));
  add(check('Peelback (P)', () => c.peel.enabled, (v) => api.setPeel({ enabled: v })));
  add(slider('radius (m)', 0.05, 3, 0.01, () => c.peel.radius, (v) => api.setPeel({ radius: v }), (v) => v.toFixed(2)));
  add(slider('slope', 0, 3, 0.01, () => c.peel.slope, (v) => api.setPeel({ slope: v }), (v) => v.toFixed(2)));
  add(slider('feather (m)', 0, 0.5, 0.005, () => c.peel.feather, (v) => api.setPeel({ feather: v }), (v) => v.toFixed(3)));
  box.appendChild(note('More options are in the View modes folder of the parameter panel.'));
  // The keys B and P change the state too: poll while the drawer is open.
  const t = setInterval(() => widgets.forEach((w) => w.update()), 400);
  return () => clearInterval(t);
}

function cleanupPanel(box: HTMLElement): (() => void) | void {
  const api = window.__xrayCleanup;
  if (!api) {
    box.appendChild(note('The cleanup feature is not available in this build.'));
    return;
  }
  // No getter for the live rules: start from the last report's rules, else the defaults, and keep our own copy in step.
  const rules: CleanupRules = JSON.parse(JSON.stringify(api.lastReport?.rules ?? defaultRules())) as CleanupRules;
  const status = statusLine(api.lastReport ? `${api.lastReport.summary}` : 'No analysis yet');
  const widgets: Widget[] = [];
  const add = (w: Widget): void => {
    widgets.push(w);
    box.appendChild(w.root);
    w.update();
  };
  const set = (patch: Record<string, unknown>): void => {
    api.setRules(patch);
    status.set('Rules changed, press Preview matches');
  };
  box.appendChild(section('Rules'));
  add(check('Floating elements', () => rules.floating.enabled, (v) => { rules.floating.enabled = v; set({ floating: { enabled: v } }); }));
  add(slider('threshold', 0, 5, 0.01, () => rules.floating.threshold, (v) => { rules.floating.threshold = v; set({ floating: { threshold: v } }); }, (v) => v.toFixed(2)));
  add(check('Tiny elements', () => rules.tiny.enabled, (v) => { rules.tiny.enabled = v; set({ tiny: { enabled: v } }); }));
  add(check('Distant strays', () => rules.strays.enabled, (v) => { rules.strays.enabled = v; set({ strays: { enabled: v } }); }));
  add(check('Duplicates', () => rules.duplicates.enabled, (v) => { rules.duplicates.enabled = v; set({ duplicates: { enabled: v } }); }));
  add(check('Degenerate', () => rules.degenerate.enabled, (v) => { rules.degenerate.enabled = v; set({ degenerate: { enabled: v } }); }));
  add(check('Proxies', () => rules.classes.proxies, (v) => { rules.classes.proxies = v; set({ classes: { proxies: v } }); }));
  add(check('Furniture', () => rules.classes.furniture, (v) => { rules.classes.furniture = v; set({ classes: { furniture: v } }); }));
  add(check('Accessories and fasteners', () => rules.classes.accessories, (v) => { rules.classes.accessories = v; set({ classes: { accessories: v } }); }));
  box.appendChild(section('Actions'));
  const after = (r: { summary: string; total: number } | null, verb: string): void => status.set(r ? `${r.summary} (${r.total} ${verb})` : 'No model');
  box.appendChild(row(
    button('Preview', () => after(api.preview(), 'previewed'), { primary: true, title: 'Tint the matches magenta' }),
    button('Hide', () => after(api.hide(), 'hidden'), { title: 'Hide the matches (non-destructive)' }),
    button('Restore', () => status.set(`Restored ${api.restore()} elements`), { title: 'Show what cleanup hid' }),
  ));
  box.appendChild(status);
  box.appendChild(note('Slider thresholds apply to the size metric chosen in the Model cleanup folder (default: largest dimension in metres).'));
  return undefined;
}

/** Register the wrapper tools. Returns an unregister function. */
export function registerBuiltinTools(): () => void {
  const offs = [
    registerTool({
      id: 'open', label: 'Open model', title: 'Open an IFC or glb file', icon: ICONS.open, order: 10,
      toggle: (app) => openModel(app),
    }),
    registerTool({
      id: 'xray', label: 'X-ray', title: 'Toggle x-ray (X)', icon: ICONS.xray, order: 30,
      toggle: (app, on) => app.setXray(on),
      isActive: (app) => app.settings.xray,
    }),
    registerTool({
      id: 'viewModes', label: 'View modes', title: 'Behind-only view and partial peelback', icon: ICONS.viewModes, order: 40,
      available: () => !!window.__xrayViewModes,
      isActive: () => !!window.__xrayViewModes && (window.__xrayViewModes.config.behind.enabled || window.__xrayViewModes.config.peel.enabled),
      panel: (box) => viewModesPanel(box),
    }),
    registerTool({
      id: 'cleanup', label: 'Cleanup', title: 'Find and hide floating or tiny debris', icon: ICONS.cleanup, order: 110,
      available: () => !!window.__xrayCleanup,
      panel: (box) => cleanupPanel(box),
    }),
  ];
  return () => offs.forEach((o) => o());
}
