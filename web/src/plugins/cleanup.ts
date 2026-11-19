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
import { mergedCleanupGeometry, mergedRayCaster, mergedSource } from '../cleanup/geometryAdapter';
import { buildCleanupPlan } from '../cleanup/plan';
import type { CleanupPlan, PlanStats } from '../cleanup/plan';
import {
  SimplifyWork, fmtBytes, previewClean, previewDecimation, previewInstances, previewInterior, previewSmallDetails,
} from '../cleanup/work';
import type { PendingEdit, SimplifyTool, ToolContext } from '../cleanup/work';
import { DETAIL_CLASSES } from '../cleanup/simplify/details';
import { showSaveDialog } from '../cleanup/saveDialog';
import { parseModel } from '../model/loader';
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

/** Settings of the simplification tools (lengths in metres). Kept for the session, not stored per model. */
export interface SimplifyOptions {
  decimate: { mode: 'target ratio' | 'max error'; ratio: number; maxError: number; minTriangles: number; sharpAngle: number };
  details: { maxSize: number; maxVolume: number; classFilter: 'any class' | 'fasteners and accessories'; cutPieces: boolean };
  interior: { directions: number; samples: number };
  weld: { distance: number; dropDegenerate: boolean; dropDuplicateFaces: boolean };
  stripProps: boolean;
}

export function defaultSimplifyOptions(): SimplifyOptions {
  return {
    decimate: { mode: 'target ratio', ratio: 0.5, maxError: 0.01, minTriangles: 200, sharpAngle: 30 },
    details: { maxSize: 0.05, maxVolume: 0, classFilter: 'any class', cutPieces: false },
    interior: { directions: 16, samples: 6 },
    weld: { distance: 0.0001, dropDegenerate: true, dropDuplicateFaces: true },
    stripProps: false,
  };
}

/** What the panel and scripts see of a pending (previewed, not yet applied) change. */
export interface PendingSummary {
  tool: SimplifyTool;
  elements: number;
  trianglesBefore: number;
  trianglesAfter: number;
  bytesBefore: number;
  bytesAfter: number;
  text: string;
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

function download(blob: Blob, name: string): void {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
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

  // simplification
  readonly simplify: SimplifyOptions = defaultSimplifyOptions();
  simplifyStatus = 'Nothing staged';
  private readonly work = new SimplifyWork();
  private pending: PendingEdit | null = null;
  private running: { aborted: boolean } | null = null;
  /** Rule names per element id of the matches that Hide matches hid, for the plan's removal reasons. */
  private readonly hideReasons = new Map<number, string[]>();
  private lastGlb: { buffer: ArrayBuffer; name: string } | null = null;

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
    this.tint(report.matches.map((m) => m.id));
    if (report.total > 0 && report.total < FRAME_LIMIT) this.frame(report.matches.map((m) => m.id));
    this.setStatus(`${report.summary} (${report.total} previewed)`);
    return report;
  }

  /** Tint these elements with the preview colour (replaces an earlier tint). */
  private tint(ids: readonly number[]): void {
    this.cancelPreview();
    const color = this.app.renderer.state.color;
    const saved = new Map<number, [number, number, number]>();
    for (const id of ids) {
      const o = id * 3;
      saved.set(id, [color[o]!, color[o + 1]!, color[o + 2]!]);
      color[o] = HIGHLIGHT[0];
      color[o + 1] = HIGHLIGHT[1];
      color[o + 2] = HIGHLIGHT[2];
    }
    this.saved = saved;
    this.app.renderer.markDirty();
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

  /** Add ids to the viewer's hide set with provenance and refresh the view. Returns how many were newly hidden by cleanup. */
  private hideIds(ids: readonly number[]): number {
    const app = this.app;
    const ov = app.controller.settings.overrides;
    const n = this.hides.hide(ov.userHides, ids);
    for (const id of ids) ov.userPins.delete(id);
    // Hidden elements stop being focus: drop them from the selection.
    const sel = app.selection;
    if (sel.some((id) => ov.userHides.has(id))) app.selectIds(sel.filter((id) => !ov.userHides.has(id)));
    app.controller.refreshOverrides();
    app.runSightlinesNow();
    app.renderer.markDirty();
    return n;
  }

  hide(): CleanupReport | null {
    this.cancelPreview();
    const report = this.analyse();
    if (!report) return null;
    const ids = report.matches.map((m) => m.id);
    const n = this.hideIds(ids);
    for (const m of report.matches) this.hideReasons.set(m.id, m.rules.slice());
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
    this.work.clear();
    this.pending = null;
    this.hideReasons.clear();
    this.setSimplifyStatus('Nothing staged');
    app.controller.refreshOverrides();
    app.runSightlinesNow();
    app.renderer.markDirty();
    this.lastOwned = 0;
    this.setStatus(`Restored ${shown.length} elements hidden by cleanup`);
    return shown.length;
  }

  /** Element ids that cleanup hid and the user has not un-hidden (read by Save IFC for the Xray_Cleanup marks). */
  ownedIds(): number[] {
    return [...this.hides.owned];
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
    download(new Blob([JSON.stringify(r, null, 2)], { type: 'application/json' }), `cleanup-${this.app.modelName}.json`);
    this.setStatus(`${r.summary} (report exported)`);
  }

  // ---------------------------------------------------------------- simplification

  setSimplifyStatus(text: string): void {
    this.simplifyStatus = text;
    this.folder?.controllersRecursive().forEach((c) => {
      if (c.property === 'simplifyStatus') c.updateDisplay();
    });
  }

  /** A simplify setting changed: the previewed change no longer matches it. */
  simplifyChanged(): void {
    if (!this.pending) return;
    this.pending = null;
    this.cancelPreview();
    this.setSimplifyStatus(this.stagedText());
  }

  get isBusy(): boolean {
    return this.running !== null;
  }

  cancelRun(): void {
    if (this.running) this.running.aborted = true;
  }

  private summarisePending(p: PendingEdit): PendingSummary {
    return { tool: p.tool, elements: p.ids.length, trianglesBefore: p.trianglesBefore, trianglesAfter: p.trianglesAfter, bytesBefore: p.bytesBefore, bytesAfter: p.bytesAfter, text: p.text };
  }

  /** Preview one tool: compute the change in chunks, tint the affected elements, keep it pending for Apply. */
  async previewTool(tool: SimplifyTool): Promise<PendingSummary | null> {
    const loaded = this.app.loaded;
    if (!loaded || this.running) return null;
    this.cancelPreview();
    this.pending = null;
    const signal = { aborted: false };
    this.running = signal;
    const o = this.simplify;
    const ctx: ToolContext = {
      src: mergedSource(loaded.geometry),
      elements: loaded.model.elements,
      work: this.work,
      chunk: { signal, onProgress: (d, t) => this.setSimplifyStatus(`Working: ${d.toLocaleString('en-US')} of ${t.toLocaleString('en-US')}`) },
    };
    this.setSimplifyStatus('Working...');
    try {
      let p: PendingEdit | null = null;
      if (tool === 'decimate') {
        p = await previewDecimation(ctx, { mode: o.decimate.mode === 'target ratio' ? 'ratio' : 'error', ratio: o.decimate.ratio, maxError: o.decimate.maxError, minTriangles: o.decimate.minTriangles, sharpAngle: o.decimate.sharpAngle });
      } else if (tool === 'details') {
        p = await previewSmallDetails(ctx, {
          maxSize: o.details.maxSize, maxVolume: o.details.maxVolume, subMeshes: o.details.cutPieces,
          classes: o.details.classFilter === 'any class' ? [] : DETAIL_CLASSES,
        });
      } else if (tool === 'interior') {
        p = await previewInterior(ctx, mergedRayCaster(loaded.geometry), { directions: o.interior.directions, samples: o.interior.samples });
      } else if (tool === 'instances') {
        p = await previewInstances(ctx);
      } else {
        p = await previewClean(ctx, { weldTolerance: o.weld.distance, dropDegenerate: o.weld.dropDegenerate, dropDuplicateFaces: o.weld.dropDuplicateFaces });
      }
      if (!p) {
        this.setSimplifyStatus('Cancelled');
        return null;
      }
      this.pending = p;
      if (p.ids.length > 0) {
        this.tint(p.ids);
        if (p.ids.length < FRAME_LIMIT) this.frame(p.ids);
      }
      this.setSimplifyStatus(p.ids.length > 0 ? `${p.text}. Press Apply.` : `${p.text}. Nothing to change.`);
      return this.summarisePending(p);
    } finally {
      this.running = null;
    }
  }

  /** Stage the previewed change. Removals also hide the elements in the viewer (Restore cleanup shows them again). */
  applyPending(): PendingSummary | null {
    const p = this.pending;
    if (!p || p.ids.length === 0) {
      this.setSimplifyStatus('Nothing previewed to apply');
      return null;
    }
    this.cancelPreview();
    if (p.removals.size > 0) this.hideIds([...p.removals.keys()]);
    this.work.commit(p);
    this.pending = null;
    this.lastOwned = this.hides.owned.size;
    this.setSimplifyStatus(`Applied. ${this.stagedText()}. Save cleaned model writes it.`);
    return this.summarisePending(p);
  }

  /** Forget the staged simplification (replacements, instances, removals) and show removed elements again. */
  resetSimplify(): void {
    this.cancelPreview();
    const ov = this.app.controller?.settings.overrides;
    if (ov && this.work.removals.size > 0) {
      this.hides.release(ov.userHides, this.work.removals.keys());
      this.app.controller.refreshOverrides();
      this.app.runSightlinesNow();
      this.app.renderer.markDirty();
    }
    this.work.clear();
    this.pending = null;
    this.setSimplifyStatus('Nothing staged');
  }

  /** The CleanupPlan of everything staged and hidden by cleanup (a pure function of the staged edits, see cleanup/plan.ts). */
  buildPlan(stripProps = this.simplify.stripProps): CleanupPlan | null {
    const loaded = this.app.loaded;
    if (!loaded) return null;
    const removed = new Map<number, string[]>();
    for (const [id, reason] of this.work.removals) removed.set(id, [reason]);
    const hides = this.app.controller?.settings.overrides.userHides;
    if (hides) for (const id of this.hides.owned) if (hides.has(id) && !removed.has(id)) removed.set(id, this.hideReasons.get(id) ?? ['cleanup']);
    return buildCleanupPlan({
      elements: loaded.model.elements,
      source: mergedSource(loaded.geometry),
      removed,
      replacements: this.work.replacements,
      groups: this.work.groups,
      stripProps,
    });
  }

  stagedText(): string {
    const plan = this.buildPlan();
    if (!plan) return 'Nothing staged';
    const s: PlanStats = plan.stats;
    if (s.removed === 0 && s.simplified === 0 && s.instanceGroups === 0) return 'Nothing staged';
    return `Staged: ${s.removed} removed, ${s.simplified} simplified, ${s.instanceGroups} instance groups; ${s.trianglesBefore.toLocaleString('en-US')} to ${s.trianglesAfter.toLocaleString('en-US')} triangles, ~${fmtBytes(s.bytesBefore)} to ~${fmtBytes(s.bytesAfter)}`;
  }

  /** Write the cleaned model as a glb and download it. */
  async saveCleaned(stripProps = this.simplify.stripProps): Promise<{ bytes: number; fileName: string; glb: ArrayBuffer }> {
    const loaded = this.app.loaded;
    const plan = this.buildPlan(stripProps);
    if (!loaded || !plan) throw new Error('No model is loaded');
    const { exportCleanedGlb } = await import('../cleanup/glbExport');
    const glb = await exportCleanedGlb(loaded.model.elements, mergedSource(loaded.geometry), plan, { stripProps });
    const fileName = `cleaned-${this.app.modelName}.glb`;
    this.lastGlb = { buffer: glb, name: `${this.app.modelName}-cleaned` };
    download(new Blob([glb], { type: 'model/gltf-binary' }), fileName);
    this.setSimplifyStatus(`Saved ${fileName}, ${fmtBytes(glb.byteLength)}`);
    return { bytes: glb.byteLength, fileName, glb };
  }

  /** Open the file that was saved last in the viewer, to check it. */
  async openSaved(): Promise<void> {
    const saved = this.lastGlb;
    if (!saved) throw new Error('Nothing saved yet');
    const loaded = await parseModel(saved.buffer.slice(0));
    this.app.openLoaded(loaded, saved.name);
  }

  openSaveDialog(): void {
    if (!this.app.loaded) return;
    showSaveDialog({
      stats: (strip) => this.buildPlan(strip)!.stats,
      save: async (strip) => {
        const r = await this.saveCleaned(strip);
        return { bytes: r.bytes, fileName: r.fileName };
      },
      openSaved: () => this.openSaved(),
      initialStrip: this.simplify.stripProps,
      onStrip: (strip) => {
        this.simplify.stripProps = strip;
        this.folder?.controllersRecursive().forEach((c) => c.updateDisplay());
      },
    });
  }

  // ---------------------------------------------------------------- model lifecycle

  onModel(): void {
    this.saved = null; // the renderer state was replaced
    this.hides.clear();
    this.work.clear();
    this.pending = null;
    this.running = null;
    this.hideReasons.clear();
    this.setSimplifyStatus('Nothing staged');
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
      /** Ids hidden by cleanup and still hidden (not the ones the user hid by hand). */
      hiddenByCleanup(): number[];
      /** The live rules (SI units: metres, m³). Treat as read-only; change them with setRules. */
      readonly rules: CleanupRules;
      /** Display unit of the length thresholds: mm, cm or m. */
      lengthUnit: LengthUnit;
      /** The simplification tools. Options are live (metres); change a field, then preview. */
      simplify: {
        readonly options: SimplifyOptions;
        preview(tool: SimplifyTool): Promise<PendingSummary | null>;
        apply(): PendingSummary | null;
        reset(): void;
        cancel(): void;
        plan(stripProps?: boolean): CleanupPlan | null;
        /** Build the glb and download it; resolves with its size. */
        save(stripProps?: boolean): Promise<{ bytes: number; fileName: string }>;
        openSaved(): Promise<void>;
        openDialog(): void;
        readonly status: string;
      };
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
    registerAction({ id: 'cleanup.save', label: 'Cleanup: save cleaned model', group: 'Cleanup', keys: [], run: () => c.openSaveDialog() });
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
      hiddenByCleanup: () => c.ownedIds(),
      get rules() {
        return c.rules;
      },
      get lengthUnit() {
        return c.lengthUnit;
      },
      set lengthUnit(u: LengthUnit) {
        c.setLengthUnit(u);
      },
      simplify: {
        get options() {
          return c.simplify;
        },
        preview: (tool) => c.previewTool(tool),
        apply: () => c.applyPending(),
        reset: () => c.resetSimplify(),
        cancel: () => c.cancelRun(),
        plan: (strip) => c.buildPlan(strip),
        save: async (strip) => {
          const r = await c.saveCleaned(strip);
          return { bytes: r.bytes, fileName: r.fileName };
        },
        openSaved: () => c.openSaved(),
        openDialog: () => c.openSaveDialog(),
        get status() {
          return c.simplifyStatus;
        },
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
    f: GUI, get: () => T, prop: keyof T & string, label: string, range: [number, number, number] | [number, null, number], onChange: () => void = changed,
  ): void => {
    const view = new Proxy({} as Record<string, number>, {
      get: (_t, k) => (k === prop ? toDisplay((get() as Record<string, number>)[prop]!, c.lengthUnit) : undefined),
      set: (_t, k, v) => {
        if (k === prop) (get() as Record<string, number>)[prop] = fromDisplay(Number(v), c.lengthUnit);
        return true;
      },
    });
    const ctl = f.add(view, prop).onChange(onChange);
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


  // Simplification tools: each previews first (tint, counts, estimated size), then applies; nothing touches the model file.
  const so = c.simplify;
  const sc = (): void => c.simplifyChanged();
  const sp = <T extends object>(get: () => T): T => proxy(get);
  const fsimp = folder.addFolder('Simplify');
  fsimp.close();
  const sst = proxy(() => c as unknown as { simplifyStatus: string });
  fsimp.add(sst, 'simplifyStatus').name('Simplify status').disable();
  const toolButtons = (f: GUI, tool: SimplifyTool): void => {
    f.add({ preview: () => void c.previewTool(tool) }, 'preview').name('Preview');
    f.add({ apply: () => void c.applyPending() }, 'apply').name('Apply');
  };

  const fdec = fsimp.addFolder('Decimate mesh');
  fdec.close();
  const dec = sp(() => so.decimate);
  fdec.add(dec, 'mode', ['target ratio', 'max error']).name('mode').onChange(sc);
  fdec.add(dec, 'ratio', 0.02, 1, 0.01).name('target ratio').onChange(sc);
  length(fdec, () => so.decimate, 'maxError', 'max error', [0, 0.5, 0.0005], sc);
  fdec.add(dec, 'minTriangles', 0, 5000, 10).name('skip below (triangles)').onChange(sc);
  fdec.add(dec, 'sharpAngle', 5, 90, 1).name('sharp edge angle').onChange(sc);
  toolButtons(fdec, 'decimate');

  const fdet = fsimp.addFolder('Small details');
  fdet.close();
  const det = sp(() => so.details);
  length(fdet, () => so.details, 'maxSize', 'max size', [0, 1, 0.001], sc);
  fdet.add(det, 'maxVolume', 0, 1, 0.0001).name('max volume (m³)').onChange(sc);
  fdet.add(det, 'classFilter', ['any class', 'fasteners and accessories']).name('class filter').onChange(sc);
  fdet.add(det, 'cutPieces').name('cut loose pieces').onChange(sc);
  toolButtons(fdet, 'details');

  const fint = fsimp.addFolder('Hidden interior');
  fint.close();
  const intr = sp(() => so.interior);
  fint.add(intr, 'directions', 6, 64, 1).name('rays per point').onChange(sc);
  fint.add(intr, 'samples', 1, 24, 1).name('points per element').onChange(sc);
  toolButtons(fint, 'interior');

  const finst = fsimp.addFolder('Instances');
  finst.close();
  toolButtons(finst, 'instances');

  const fweld = fsimp.addFolder('Weld and clean');
  fweld.close();
  const weld = sp(() => so.weld);
  length(fweld, () => so.weld, 'distance', 'weld distance', [0, 0.01, 0.00001], sc);
  fweld.add(weld, 'dropDegenerate').name('drop degenerate').onChange(sc);
  fweld.add(weld, 'dropDuplicateFaces').name('drop duplicate faces').onChange(sc);
  toolButtons(fweld, 'weld');

  fsimp.add({ cancel: () => c.cancelRun() }, 'cancel').name('Cancel run');
  fsimp.add({ reset: () => c.resetSimplify() }, 'reset').name('Undo simplification');
  fsimp.add(proxy(() => c.simplify), 'stripProps').name('strip property data');

  const actions = {
    preview: () => void c.preview(),
    hide: () => void c.hide(),
    restore: () => void c.restore(),
    select: () => c.select(),
    exportReport: () => c.exportReport(),
    save: () => c.openSaveDialog(),
  };
  folder.add(actions, 'preview').name('Preview matches');
  folder.add(actions, 'hide').name('Hide matches');
  folder.add(actions, 'restore').name('Restore cleanup');
  folder.add(actions, 'select').name('Select matches');
  folder.add(actions, 'exportReport').name('Export report');
  folder.add(actions, 'save').name('Save cleaned model');
  const st = proxy(() => c as unknown as { status: string });
  folder.add(st, 'status').name('Cleanup status').disable();
  const al = proxy(() => c as unknown as { applyOnLoad: boolean });
  folder.add(al, 'applyOnLoad').name('apply on load').onChange(() => c.save());
}
