// Model cleanup plugin: finds floating or tiny debris, distant strays, duplicates, degenerate elements and unwanted
// class groups, previews them as a tint and hides them non-destructively through controller.settings.overrides.userHides
// (merged with provenance, see cleanup/hides.ts). Analysis lives in cleanup/analysis.ts.
//
//   window.__xrayCleanup = { analyse(rules?), preview(), hide(), restore(), lastReport }

import type GUI from 'lil-gui';
import type { AppPlugin, ViewerApp } from '../app';
import { registerAction } from '../input/actions';
import { registerParamSection } from '../ui/params';
import { boxFromTuple, requestFrame } from '../ui/fit';
import { unionBounds } from '../selectionSets';
import {
  FLOATING_MODES, METRIC_DEFAULT_THRESHOLD, SIZE_METRICS, analyse as runAnalysis, defaultRules, summarise,
} from '../cleanup/analysis';
import type { CleanupRules, CleanupResult, SizeMetric } from '../cleanup/analysis';
import { CleanupHides } from '../cleanup/hides';
import { mergedCleanupGeometry } from '../cleanup/geometryAdapter';
import {
  DEFAULT_LENGTH_UNIT, LENGTH_UNITS, displayRange, fromDisplay, isLengthUnit, metricFromDisplay, metricIsLength, metricLabel, metricToDisplay,
  metricUnit, toDisplay, withUnit,
} from '../cleanup/units';
import type { LengthUnit } from '../cleanup/units';

export interface CleanupReport {
  schema: 'xray-cleanup/1';
  model: string;
  createdAt: string;
  rules: CleanupRules;
  counts: CleanupResult['counts'];
  summary: string;
  total: number;
  analysisMs: number;
  matches: Array<{ id: number; globalId: string; ifcClass: string; name: string | null; rules: string[]; reasons: string[] }>;
}

interface Persisted {
  rules: CleanupRules;
  thresholds: Record<string, number>;
  applyOnLoad: boolean;
}

const HIGHLIGHT: [number, number, number] = [1, 0.1, 0.75];
const FRAME_LIMIT = 50;
const STATUS_IDLE = 'No analysis yet';
/** The length unit of the cleanup thresholds is a display preference of the viewer, not of a model. */
const UNIT_KEY = 'xray.cleanup.lengthUnit';

function store(): Storage | null {
  try {
    const s = window.localStorage;
    s.getItem('xray.probe');
    return s;
  } catch {
    return null;
  }
}

function num(v: unknown, d: number, lo = 0): number {
  return typeof v === 'number' && Number.isFinite(v) && v >= lo ? v : d;
}
function bool(v: unknown, d: boolean): boolean {
  return typeof v === 'boolean' ? v : d;
}
function obj(v: unknown): Record<string, unknown> {
  return v && typeof v === 'object' ? (v as Record<string, unknown>) : {};
}

/** Validate untrusted rule data into a full CleanupRules (unknown or bad fields fall back to defaults). */
export function sanitiseRules(v: unknown, bad?: string[], path = 'rules'): CleanupRules {
  const d = defaultRules();
  const o = obj(v);
  const f = obj(o['floating']);
  const metric = (SIZE_METRICS as readonly string[]).includes(f['metric'] as string) ? (f['metric'] as SizeMetric) : d.floating.metric;
  const mode = (FLOATING_MODES as readonly string[]).includes(f['mode'] as string) ? (f['mode'] as CleanupRules['floating']['mode']) : d.floating.mode;
  if (f['metric'] !== undefined && metric !== f['metric']) bad?.push(`${path}.floating.metric`);
  if (f['mode'] !== undefined && mode !== f['mode']) bad?.push(`${path}.floating.mode`);
  const t = obj(o['tiny']);
  const s = obj(o['strays']);
  const c = obj(o['classes']);
  return {
    floating: {
      enabled: bool(f['enabled'], d.floating.enabled),
      metric,
      threshold: num(f['threshold'], METRIC_DEFAULT_THRESHOLD[metric]),
      mode,
      contactTolerance: num(f['contactTolerance'], d.floating.contactTolerance),
      precise: bool(f['precise'], d.floating.precise),
    },
    tiny: { enabled: bool(t['enabled'], d.tiny.enabled), maxSize: num(t['maxSize'], d.tiny.maxSize) },
    strays: {
      enabled: bool(s['enabled'], d.strays.enabled),
      factor: num(s['factor'], d.strays.factor, 0.1),
      minGap: num(s['minGap'], d.strays.minGap),
      maxSize: num(s['maxSize'], d.strays.maxSize),
    },
    duplicates: { enabled: bool(obj(o['duplicates'])['enabled'], d.duplicates.enabled) },
    degenerate: { enabled: bool(obj(o['degenerate'])['enabled'], d.degenerate.enabled) },
    classes: { proxies: bool(c['proxies'], false), furniture: bool(c['furniture'], false), accessories: bool(c['accessories'], false) },
  };
}

function mergeRules(base: CleanupRules, patch: unknown): CleanupRules {
  const p = obj(patch);
  const out = JSON.parse(JSON.stringify(base)) as CleanupRules;
  for (const k of Object.keys(out) as Array<keyof CleanupRules>) {
    const sub = obj(p[k]);
    Object.assign(out[k], sub);
  }
  return sanitiseRules(out);
}

class CleanupController {
  rules = defaultRules();
  thresholds: Record<string, number> = { ...METRIC_DEFAULT_THRESHOLD };
  applyOnLoad = false;
  /** Display unit of every length threshold (rules keep metres). */
  lengthUnit: LengthUnit = DEFAULT_LENGTH_UNIT;
  status = STATUS_IDLE;
  lastReport: CleanupReport | null = null;
  private last: CleanupResult | null = null;
  private readonly hides = new CleanupHides();
  private saved: Map<number, [number, number, number]> | null = null;
  private folder: GUI | null = null;
  private lastOwned = 0;
  private lastPrune = 0;

  /** Panel controls that show a length; they get a new label and range when the unit changes. */
  readonly unitListeners: Array<() => void> = [];

  constructor(private readonly app: ViewerApp) {
    try {
      const u = store()?.getItem(UNIT_KEY);
      if (isLengthUnit(u)) this.lengthUnit = u;
    } catch {
      /* ignore */
    }
  }

  setLengthUnit(unit: LengthUnit): void {
    if (!isLengthUnit(unit)) return;
    this.lengthUnit = unit;
    try {
      store()?.setItem(UNIT_KEY, unit);
    } catch {
      /* ignore */
    }
    this.refreshGui();
  }

  attach(folder: GUI): void {
    this.folder = folder;
  }

  // ---------------------------------------------------------------- persistence

  private key(): string {
    return `xray.cleanup.${this.app.modelName}`;
  }

  load(): void {
    this.rules = defaultRules();
    this.thresholds = { ...METRIC_DEFAULT_THRESHOLD };
    this.applyOnLoad = false;
    try {
      const raw = store()?.getItem(this.key());
      if (raw) {
        const p = JSON.parse(raw) as Partial<Persisted>;
        this.rules = sanitiseRules(p.rules);
        for (const [k, v] of Object.entries(obj(p.thresholds))) if (k in this.thresholds && typeof v === 'number' && v >= 0) this.thresholds[k] = v;
        this.applyOnLoad = p.applyOnLoad === true;
      }
    } catch {
      /* ignore corrupt storage */
    }
    this.thresholds[this.rules.floating.metric] = this.rules.floating.threshold;
  }

  save(): void {
    this.thresholds[this.rules.floating.metric] = this.rules.floating.threshold;
    try {
      const p: Persisted = { rules: this.rules, thresholds: this.thresholds, applyOnLoad: this.applyOnLoad };
      store()?.setItem(this.key(), JSON.stringify(p));
    } catch {
      /* ignore */
    }
  }

  /** The settings section for the params document (rules only, not the match list). */
  collect(): unknown {
    return { rules: this.rules, applyOnLoad: this.applyOnLoad };
  }

  applyParams(value: unknown, bad: string[], path: string): void {
    const o = obj(value);
    if (o['rules'] !== undefined) {
      this.cancelPreview();
      this.rules = sanitiseRules(o['rules'], bad, `${path}.rules`);
      this.thresholds[this.rules.floating.metric] = this.rules.floating.threshold;
    }
    if (o['applyOnLoad'] !== undefined) this.applyOnLoad = o['applyOnLoad'] === true;
    this.last = null;
    this.setStatus(STATUS_IDLE);
    this.save();
    this.refreshGui();
  }

  // ---------------------------------------------------------------- rule changes

  /** Called by the GUI after any rule control changed. */
  rulesChanged(): void {
    this.cancelPreview();
    this.last = null;
    this.save();
    this.setStatus(this.hides.owned.size > 0 ? `${this.hiddenText()}; rules changed` : 'Rules changed, press Preview matches');
  }

  setRules(patch: unknown): void {
    this.rules = mergeRules(this.rules, patch);
    this.refreshGui();
    this.rulesChanged();
  }

  setMetric(metric: SizeMetric): void {
    this.thresholds[this.rules.floating.metric] = this.rules.floating.threshold;
    this.rules.floating.metric = metric;
    this.rules.floating.threshold = this.thresholds[metric] ?? METRIC_DEFAULT_THRESHOLD[metric];
    this.refreshGui();
    this.rulesChanged();
  }

  // ---------------------------------------------------------------- analysis

  analyse(patch?: unknown): CleanupReport | null {
    const app = this.app;
    const loaded = app.loaded;
    if (!loaded) return null;
    const rules = patch === undefined ? this.rules : mergeRules(this.rules, patch);
    const els = loaded.model.elements;
    const geo = mergedCleanupGeometry(loaded.geometry, app.geometry);
    const res = runAnalysis(els, rules, geo);
    const report: CleanupReport = {
      schema: 'xray-cleanup/1',
      model: app.modelName,
      createdAt: new Date().toISOString(),
      rules: JSON.parse(JSON.stringify(rules)) as CleanupRules,
      counts: res.counts,
      summary: summarise(res.counts),
      total: res.ids.length,
      analysisMs: res.ms,
      matches: res.ids.map((id) => {
        const e = els[id]!;
        const m = res.matches.get(id)!;
        return { id, globalId: e.globalId, ifcClass: e.ifcClass, name: e.name ?? null, rules: m.rules, reasons: m.reasons };
      }),
    };
    this.last = res;
    this.lastReport = report;
    return report;
  }

  private ensureReport(): CleanupReport | null {
    if (this.last && this.lastReport) return this.lastReport;
    return this.analyse();
  }

  // ---------------------------------------------------------------- preview

  preview(): CleanupReport | null {
    this.cancelPreview();
    const report = this.analyse();
    if (!report) return null;
    const app = this.app;
    const color = app.renderer.state.color;
    const saved = new Map<number, [number, number, number]>();
    for (const m of report.matches) {
      const o = m.id * 3;
      saved.set(m.id, [color[o]!, color[o + 1]!, color[o + 2]!]);
      color[o] = HIGHLIGHT[0];
      color[o + 1] = HIGHLIGHT[1];
      color[o + 2] = HIGHLIGHT[2];
    }
    this.saved = saved;
    app.renderer.markDirty();
    if (report.total > 0 && report.total < FRAME_LIMIT) this.frame(report.matches.map((m) => m.id));
    this.setStatus(`${report.summary} (${report.total} previewed)`);
    return report;
  }

  cancelPreview(): void {
    const saved = this.saved;
    if (!saved) return;
    this.saved = null;
    const color = this.app.renderer.state.color;
    for (const [id, c] of saved) {
      color[id * 3] = c[0];
      color[id * 3 + 1] = c[1];
      color[id * 3 + 2] = c[2];
    }
    this.app.renderer.markDirty();
  }

  private frame(ids: number[]): void {
    const b = unionBounds(this.app.controller.model, ids);
    if (!b) return;
    requestFrame(this.app.renderer.camera, this.app.renderer.controls, boxFromTuple(b));
    this.app.renderer.markDirty();
  }

  // ---------------------------------------------------------------- hide and restore

  hide(): CleanupReport | null {
    this.cancelPreview();
    const report = this.analyse();
    if (!report) return null;
    const app = this.app;
    const ov = app.controller.settings.overrides;
    const ids = report.matches.map((m) => m.id);
    const n = this.hides.hide(ov.userHides, ids);
    for (const id of ids) ov.userPins.delete(id);
    // Hidden elements stop being focus: drop them from the selection.
    const sel = app.selection;
    if (sel.some((id) => ov.userHides.has(id))) app.selectIds(sel.filter((id) => !ov.userHides.has(id)));
    app.controller.refreshOverrides();
    app.runSightlinesNow();
    app.renderer.markDirty();
    this.lastOwned = this.hides.owned.size;
    this.setStatus(`${report.summary}; hid ${n} (${ids.length - n} already hidden by you)`);
    return report;
  }

  restore(): number {
    this.cancelPreview();
    const app = this.app;
    if (!app.controller) return 0;
    const ov = app.controller.settings.overrides;
    const shown = this.hides.restore(ov.userHides);
    app.controller.refreshOverrides();
    app.runSightlinesNow();
    app.renderer.markDirty();
    this.lastOwned = 0;
    this.setStatus(`Restored ${shown.length} elements hidden by cleanup`);
    return shown.length;
  }

  hiddenText(): string {
    return `${this.hides.owned.size} hidden by cleanup`;
  }

  select(): void {
    const r = this.ensureReport();
    if (!r) return;
    this.app.selectIds(r.matches.map((m) => m.id));
    this.setStatus(`${r.summary} (${r.total} selected)`);
  }

  exportReport(): void {
    const r = this.ensureReport();
    if (!r) return;
    const blob = new Blob([JSON.stringify(r, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `cleanup-${this.app.modelName}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    this.setStatus(`${r.summary} (report exported)`);
  }

  // ---------------------------------------------------------------- model lifecycle

  onModel(): void {
    this.saved = null; // the renderer state was replaced
    this.hides.clear();
    this.last = null;
    this.lastReport = null;
    this.lastOwned = 0;
    this.load();
    this.setStatus(STATUS_IDLE);
    this.refreshGui();
    if (this.applyOnLoad) this.hide();
  }

  /** Throttled bookkeeping: forget owned ids the user unhid by hand. */
  tick(now: number): void {
    if (now - this.lastPrune < 250 || this.hides.owned.size === 0) return;
    this.lastPrune = now;
    if (this.hides.prune(this.app.controller.settings.overrides.userHides) && this.hides.owned.size !== this.lastOwned) {
      this.lastOwned = this.hides.owned.size;
      this.setStatus(this.lastOwned > 0 ? this.hiddenText() : 'Nothing hidden by cleanup');
    }
  }

  // ---------------------------------------------------------------- GUI plumbing

  setStatus(text: string): void {
    this.status = text;
    this.folder?.controllersRecursive().forEach((c) => {
      if (c.property === 'status') c.updateDisplay();
    });
  }

  refreshGui(): void {
    for (const f of this.unitListeners) f();
    this.folder?.controllersRecursive().forEach((c) => c.updateDisplay());
  }
}

let ctl: CleanupController | null = null;

declare global {
  interface Window {
    __xrayCleanup?: {
      analyse(rules?: unknown): CleanupReport | null;
      /** Replace the stored rules (merged over the current ones), update the panel, persist. */
      setRules(rules: unknown): void;
      preview(): CleanupReport | null;
      hide(): CleanupReport | null;
      restore(): number;
      readonly lastReport: CleanupReport | null;
      /** The live rules (SI units: metres, m³). Treat as read-only; change them with setRules. */
      readonly rules: CleanupRules;
      /** Display unit of the length thresholds: mm, cm or m. */
      lengthUnit: LengthUnit;
    };
  }
}

export const cleanupPlugin: AppPlugin = {
  name: 'cleanup',

  install(app: ViewerApp): void {
    const c = new CleanupController(app);
    ctl = c;
    const gui = app.panel;
    if (gui) buildGui(gui, c);

    registerParamSection('cleanup', {
      collect: () => c.collect(),
      apply: (v, bad, path) => c.applyParams(v, bad, path),
    });
    registerAction({ id: 'cleanup.preview', label: 'Cleanup: preview matches', group: 'Cleanup', keys: [], run: () => void c.preview() });
    registerAction({ id: 'cleanup.hide', label: 'Cleanup: hide matches', group: 'Cleanup', keys: [], run: () => void c.hide() });
    registerAction({ id: 'cleanup.restore', label: 'Cleanup: restore hidden', group: 'Cleanup', keys: [], run: () => void c.restore() });

    window.__xrayCleanup = {
      analyse: (rules) => c.analyse(rules),
      setRules: (rules) => c.setRules(rules),
      preview: () => c.preview(),
      hide: () => c.hide(),
      restore: () => c.restore(),
      get lastReport() {
        return c.lastReport;
      },
      get rules() {
        return c.rules;
      },
      get lengthUnit() {
        return c.lengthUnit;
      },
      set lengthUnit(u: LengthUnit) {
        c.setLengthUnit(u);
      },
    };
  },

  onModel(): void {
    ctl?.onModel();
  },

  afterFrame(_app: ViewerApp, now: number): void {
    ctl?.tick(now);
  },
};

function buildGui(gui: GUI, c: CleanupController): void {
  const folder = gui.addFolder('Model cleanup');
  folder.close();
  c.attach(folder);
  const changed = (): void => c.rulesChanged();

  // Controllers bind to c.rules objects, which load() replaces; bind through stable proxies instead.
  const proxy = <T extends object>(get: () => T): T =>
    new Proxy({} as T, {
      get: (_t, k) => (get() as Record<string | symbol, unknown>)[k],
      set: (_t, k, v) => {
        (get() as Record<string | symbol, unknown>)[k] = v;
        return true;
      },
    });
  // Lengths: the rules keep metres, the controls show the chosen unit. Each control keeps its label base and range in
  // metres and is relabelled ("max size (mm)") when the unit changes. The help lookup maps "(mm)" and "(cm)" to "(m)".
  const length = <T extends object>(
    f: GUI, get: () => T, prop: keyof T & string, label: string, range: [number, number, number] | [number, null, number],
  ): void => {
    const view = new Proxy({} as Record<string, number>, {
      get: (_t, k) => (k === prop ? toDisplay((get() as Record<string, number>)[prop]!, c.lengthUnit) : undefined),
      set: (_t, k, v) => {
        if (k === prop) (get() as Record<string, number>)[prop] = fromDisplay(Number(v), c.lengthUnit);
        return true;
      },
    });
    const ctl = f.add(view, prop).onChange(changed);
    const sync = (): void => {
      const [lo, hi, step] = range;
      const r = displayRange(lo, hi ?? 0, step, c.lengthUnit);
      ctl.min(r.min).step(r.step);
      if (hi !== null) ctl.max(r.max);
      ctl.name(withUnit(label, c.lengthUnit));
      ctl.updateDisplay();
    };
    sync();
    c.unitListeners.push(sync);
  };

  const unitView = new Proxy({} as { lengthUnit: LengthUnit }, {
    get: (_t, k) => (k === 'lengthUnit' ? c.lengthUnit : undefined),
    set: (_t, k, v) => {
      if (k === 'lengthUnit') c.setLengthUnit(v as LengthUnit);
      return true;
    },
  });
  folder.add(unitView, 'lengthUnit', [...LENGTH_UNITS]).name('length unit');

  const fl = proxy(() => c.rules.floating);
  const ff = folder.addFolder('Floating');
  ff.add(fl, 'enabled').name('enabled').onChange(changed);
  const metricOptions = Object.fromEntries(SIZE_METRICS.map((m) => [metricLabel(m), m]));
  ff.add(fl, 'metric', metricOptions).name('size metric').onChange((v: SizeMetric) => c.setMetric(v));
  // The floating threshold: a length (follows the unit), a volume in m³ or a triangle count.
  const thView = new Proxy({} as { threshold: number }, {
    get: (_t, k) => (k === 'threshold' ? metricToDisplay(c.rules.floating.metric, c.rules.floating.threshold, c.lengthUnit) : undefined),
    set: (_t, k, v) => {
      if (k === 'threshold') c.rules.floating.threshold = metricFromDisplay(c.rules.floating.metric, Number(v), c.lengthUnit);
      return true;
    },
  });
  const th = ff.add(thView, 'threshold').min(0).onChange(changed);
  const syncThreshold = (): void => {
    const m = c.rules.floating.metric;
    th.step(metricIsLength(m) ? toDisplay(0.01, c.lengthUnit) : m === 'triangle count' ? 1 : 0.001);
    th.name(withUnit('threshold', metricUnit(m, c.lengthUnit)));
    th.updateDisplay();
  };
  syncThreshold();
  c.unitListeners.push(syncThreshold);
  ff.add(fl, 'mode', [...FLOATING_MODES]).name('mode').onChange(changed);
  length(ff, () => c.rules.floating, 'contactTolerance', 'contact tolerance', [0, 0.5, 0.001]);
  ff.add(fl, 'precise').name('precise contacts').onChange(changed);

  const ft = folder.addFolder('Tiny');
  const tiny = proxy(() => c.rules.tiny);
  ft.add(tiny, 'enabled').name('enabled').onChange(changed);
  length(ft, () => c.rules.tiny, 'maxSize', 'max size', [0, 1, 0.001]);

  const fs = folder.addFolder('Distant strays');
  const strays = proxy(() => c.rules.strays);
  fs.add(strays, 'enabled').name('enabled').onChange(changed);
  fs.add(strays, 'factor', 1, 50, 0.5).name('distance factor (× radius)').onChange(changed);
  length(fs, () => c.rules.strays, 'minGap', 'min gap', [0, null, 0.1]);
  length(fs, () => c.rules.strays, 'maxSize', 'max size', [0, null, 0.01]);

  const fd = folder.addFolder('Duplicates');
  fd.add(proxy(() => c.rules.duplicates), 'enabled').name('enabled').onChange(changed);

  const fg = folder.addFolder('Degenerate');
  fg.add(proxy(() => c.rules.degenerate), 'enabled').name('enabled').onChange(changed);

  const fc = folder.addFolder('Classes');
  const classes = proxy(() => c.rules.classes);
  fc.add(classes, 'proxies').name('proxies').onChange(changed);
  fc.add(classes, 'furniture').name('furniture').onChange(changed);
  fc.add(classes, 'accessories').name('accessories and fasteners').onChange(changed);

  const actions = {
    preview: () => void c.preview(),
    hide: () => void c.hide(),
    restore: () => void c.restore(),
    select: () => c.select(),
    exportReport: () => c.exportReport(),
  };
  folder.add(actions, 'preview').name('Preview matches');
  folder.add(actions, 'hide').name('Hide matches');
  folder.add(actions, 'restore').name('Restore cleanup');
  folder.add(actions, 'select').name('Select matches');
  folder.add(actions, 'exportReport').name('Export report');
  const st = proxy(() => c as unknown as { status: string });
  folder.add(st, 'status').name('Cleanup status').disable();
  const al = proxy(() => c as unknown as { applyOnLoad: boolean });
  folder.add(al, 'applyOnLoad').name('apply on load').onChange(() => c.save());
}
