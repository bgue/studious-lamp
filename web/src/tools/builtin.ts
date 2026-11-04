// Toolbar wrappers for features that already live elsewhere: open a model, x-ray, view modes and cleanup.
// They talk to those features through their public hooks (window.__xrayViewModes, window.__xrayCleanup, the
// "Open model" panel), so they stay thin.

import type { ViewerApp } from '../app';
import { defaultRules } from '../cleanup/analysis';
import type { CleanupRules } from '../cleanup/analysis';
import { LENGTH_UNITS, displayRange, fromDisplay, metricFromDisplay, metricIsLength, metricToDisplay, metricUnit, toDisplay, withUnit } from '../cleanup/units';
import type { LengthUnit } from '../cleanup/units';
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
  // The live rules keep SI units (metres, m³); lengths show in the unit the user picks here or in the Model cleanup folder.
  const live = (): CleanupRules => api.rules ?? api.lastReport?.rules ?? defaultRules();
  const unit = (): LengthUnit => api.lengthUnit ?? 'm';
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
  const num = (v: number): string => String(Number(v.toPrecision(4)));
  /** A length slider: range in metres, label and value in the display unit. */
  const length = (label: string, lo: number, hi: number, step: number, get: () => number, put: (m: number) => void): Widget => {
    const r = displayRange(lo, hi, step, unit());
    return slider(withUnit(label, unit()), r.min, r.max, r.step, () => toDisplay(get(), unit()), (v) => put(fromDisplay(v, unit())), num);
  };
  const render = (): void => {
    box.textContent = '';
    widgets.length = 0;
    box.appendChild(section('Rules'));
    add(select('length unit', LENGTH_UNITS, unit, (v) => {
      api.lengthUnit = v;
      render();
    }));
    add(check('Floating elements', () => live().floating.enabled, (v) => set({ floating: { enabled: v } })));
    const metric = live().floating.metric;
    const th = metricIsLength(metric) ? displayRange(0, 5, 0.01, unit()) : metric === 'triangle count' ? { min: 0, max: 5000, step: 10 } : { min: 0, max: 1, step: 0.001 };
    add(slider(withUnit('threshold', metricUnit(metric, unit())), th.min, th.max, th.step,
      () => metricToDisplay(metric, live().floating.threshold, unit()),
      (v) => set({ floating: { threshold: metricFromDisplay(metric, v, unit()) } }), num));
    add(check('Tiny elements', () => live().tiny.enabled, (v) => set({ tiny: { enabled: v } })));
    add(length('max size', 0, 1, 0.001, () => live().tiny.maxSize, (m) => set({ tiny: { maxSize: m } })));
    add(check('Distant strays', () => live().strays.enabled, (v) => set({ strays: { enabled: v } })));
    add(slider('distance factor (× radius)', 1, 50, 0.5, () => live().strays.factor, (v) => set({ strays: { factor: v } }), num));
    add(length('min gap', 0, 200, 0.5, () => live().strays.minGap ?? 0, (m) => set({ strays: { minGap: m } })));
    add(check('Duplicates', () => live().duplicates.enabled, (v) => set({ duplicates: { enabled: v } })));
    add(check('Degenerate', () => live().degenerate.enabled, (v) => set({ degenerate: { enabled: v } })));
    add(check('Proxies', () => live().classes.proxies, (v) => set({ classes: { proxies: v } })));
    add(check('Furniture', () => live().classes.furniture, (v) => set({ classes: { furniture: v } })));
    add(check('Accessories and fasteners', () => live().classes.accessories, (v) => set({ classes: { accessories: v } })));
    box.appendChild(section('Actions'));
    const after = (r: { summary: string; total: number } | null, verb: string): void => status.set(r ? `${r.summary} (${r.total} ${verb})` : 'No model');
    box.appendChild(row(
      button('Preview', () => after(api.preview(), 'previewed'), { primary: true, title: 'Tint the matches magenta' }),
      button('Hide', () => after(api.hide(), 'hidden'), { title: 'Hide the matches (non-destructive)' }),
      button('Restore', () => status.set(`Restored ${api.restore()} elements`), { title: 'Show what cleanup hid' }),
    ));
    box.appendChild(status);
    box.appendChild(note('The threshold uses the size metric of the Model cleanup folder. More options, such as the contact tolerance, are there too.'));
  };
  render();
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
