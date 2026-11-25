// The schedule workflow of the 4D tab (no DOM): load a P6 schedule (.xer), configure how it describes location, trade and zone, link it to the
// model, review the links, set the film style, play, scrub and record, and write the links back into the IFC. The mapping tool
// (controller.ts) holds the assignments; the pure pipeline is src/schedule (xer, model, link, report, plan). The panel (schedulePanel.ts)
// draws this; plugins/map4d.ts installs it and exposes window.__xray4dSchedule. The links, config and schedule persist per model
// (scheduleStore.ts).

import type { ViewerApp } from '../app';
import { registerPlan } from '../anim/fourd/plans';
import { makeFourDScore } from '../anim/fourd/api';
import { mapSpan, planTimeAt, secondsAtPlan } from '../anim/fourd/timeline';
import { getScorePlayer } from '../anim/score';
import type { Cue, Score } from '../anim/score';
import { loadedIdentity, identityKey } from '../markup/scope';
import { runQuery } from '../query';
import { readTaskAttr } from '../schedule/attrs';
import { fromSceneModel } from '../schedule/model';
import type { FourDModel, SceneLike } from '../schedule/model';
import { linkSchedule } from '../schedule/link';
import { buildPlan } from '../schedule/plan';
import { formatDate } from '../schedule/planTime';
import { buildReport, renderReportHtml } from '../schedule/report';
import type { LinkReport } from '../schedule/report';
import { listXerProjects, parseXer } from '../schedule/xer';
import { buildWorkSchedule } from '../ifcsave/workSchedule';
import { readNativeTasks } from '../ifcsave/nativeTasks';
import { sourcesOf } from '../ifcsave/source';
import type { WorkScheduleSave } from '../ifcsave/workSchedule';
import type { ActivityLink, FourDConfig, FourDLinks, FourDPlan, FourDStyle, Schedule, ScheduleProject, TaskType } from '../schedule/types';
import { colourOf } from './values';
import type { Map4dController } from './controller';
import { direct } from './directorHook';
import { filmName, filmScript } from './filmScript';
import type { FilmDirected } from './filmScript';
import { ACTIVITY_IDS_PROPERTY, activityIdsMap } from './ifcio';
import { countLinks, decideLink, decisionLinks, parseLinks, serializeLinks } from './linkReview';
import { emptyConfig, guessConfig, parseConfig, serializeConfig, setNotModelled, setStyle } from './scheduleConfig';
import type { ParsedConfig } from './scheduleConfig';
import { MAX_STORED_XER, ScheduleStore } from './scheduleStore';
import type { ScheduleRecord } from './scheduleStore';
import type { ReviewStatus } from '../schedule/types';

export interface ScheduleSummary {
  project: string;
  projectName?: string;
  dataDate?: string;
  fileName: string;
  hash: string;
  tasks: number;
  byType: Partial<Record<TaskType, number>>;
  wbs: number;
  relations: number;
  codeTypes: Array<{ name: string; values: number }>;
  udfs: string[];
  warnings: number;
}

export interface LinkSummary {
  elements: { considered: number; linked: number; tied: number; unlinked: number; ratio: number };
  activities: { total: number; linked: number; suggestedOnly: number; unlinked: number; ratio: number; notModelled: number };
  ties: number;
  proposed: number;
  accepted: number;
  rejected: number;
}

export interface PlayResult { ok: boolean; message: string }

export const SAMPLE_4D_MODEL = 'fzk-haus';

const planName = (model: string): string => `4d:${model}`;

export class ScheduleController {
  schedule: Schedule | null = null;
  fileName = '';
  config: FourDConfig = emptyConfig();
  links: FourDLinks | null = null;
  report: LinkReport | null = null;
  plan: FourDPlan | null = null;
  /** Projects of a file that holds several, waiting for a choice. */
  pendingProjects: ScheduleProject[] | null = null;
  /** Why the film does not do what the style asks (no director in this build). */
  note = '';
  persistent = false;
  readonly store = new ScheduleStore();
  private bytes: Uint8Array | null = null;
  private pendingName = '';
  private key: string | null = null;
  private token = 0;
  private ready_: Promise<void> = Promise.resolve();
  private listeners = new Set<() => void>();
  private saveTimer: ReturnType<typeof setTimeout> | null = null;
  private modelCache: { src: unknown; model: FourDModel } | null = null;
  private lastScore: Score | null = null;
  private playDur = 0;

  constructor(private readonly app: ViewerApp, readonly map: Map4dController) {}

  ready(): Promise<void> { return Promise.all([this.ready_, this.nativeReady]).then(() => undefined); }
  private nativeReady: Promise<void> = Promise.resolve();
  onChange(cb: () => void): () => void { this.listeners.add(cb); return () => this.listeners.delete(cb); }
  private emit(): void { for (const l of [...this.listeners]) l(); }

  get hasModel(): boolean { return !!this.app.loaded; }

  // ------------------------------------------------------------ the model changed

  /** A new model: forget the schedule of the last one and restore the stored work of this one. */
  onModel(): void {
    const my = ++this.token;
    this.stopPlay();
    this.schedule = null; this.fileName = ''; this.bytes = null; this.links = null; this.report = null; this.plan = null; this.pendingProjects = null;
    this.config = emptyConfig();
    this.modelCache = null; this.note = '';
    this.key = null;
    this.native = null;
    if (!this.app.loaded) { this.emit(); return; }
    this.nativeReady = this.readNative(my);
    this.key = identityKey(loadedIdentity(this.app as never));
    this.ready_ = (async () => {
      const rec = await this.store.get(this.key!);
      if (my !== this.token) return;
      this.persistent = this.store.persistent;
      if (rec) {
        if (rec.config) this.config = rec.config;
        if (rec.file?.bytes) {
          try {
            this.schedule = parseXer(new Uint8Array(rec.file.bytes), { project: rec.file.project });
            this.bytes = new Uint8Array(rec.file.bytes);
            this.fileName = rec.file.name;
          } catch { this.schedule = null; }
        }
        if (rec.links && this.schedule && rec.links.schedule?.source_hash === this.schedule.sourceHash) {
          this.links = rec.links;
          this.refreshReport();
        }
      }
      this.emit();
    })();
    this.emit();
  }

  // ------------------------------------------------------------ the model view

  /** The model as the linker, the report and the plan see it. */
  fourDModel(): FourDModel | null {
    if (!this.app.loaded) return null;
    const src = this.app.controller.model;
    if (this.modelCache?.src === src) return this.modelCache.model;
    const identity = loadedIdentity(this.app as never);
    const model = fromSceneModel(src as unknown as SceneLike, { identityKey: identityKey(identity), name: identity?.name ?? this.app.modelName });
    this.modelCache = { src, model };
    return model;
  }

  // ------------------------------------------------------------ the schedule

  /** Read an XER file. A file with several projects waits for `chooseProject` (see `pendingProjects`). */
  loadXer(input: Uint8Array | string, name: string, project?: string): { ok: boolean; message: string } {
    const data = typeof input === 'string' ? new TextEncoder().encode(input) : input;
    let projects: ScheduleProject[];
    try { projects = listXerProjects(data); } catch (e) { return { ok: false, message: `${name}: ${e instanceof Error ? e.message : String(e)}` }; }
    if (projects.length === 0) return { ok: false, message: `${name} is not a usable XER file: it has no project.` };
    const wanted = project ?? (this.config.schedule.project && projects.some((p) => p.shortName === this.config.schedule.project) ? this.config.schedule.project : undefined);
    if (projects.length > 1 && !wanted) {
      this.bytes = data; this.pendingName = name; this.pendingProjects = projects;
      this.emit();
      return { ok: true, message: `${name} holds ${projects.length} projects. Pick one.` };
    }
    let schedule: Schedule;
    try { schedule = parseXer(data, wanted !== undefined ? { project: wanted } : {}); } catch (e) { return { ok: false, message: `${name}: ${e instanceof Error ? e.message : String(e)}` }; }
    const changed = this.schedule?.sourceHash !== schedule.sourceHash;
    this.pendingProjects = null;
    this.schedule = schedule; this.bytes = data; this.fileName = name;
    if (changed) { this.links = null; this.report = null; }
    this.plan = null;
    this.config = guessConfig(schedule, this.config);
    this.changed();
    return { ok: true, message: `Read ${name}: project ${schedule.project.shortName}, ${schedule.tasks.length} activities.` };
  }

  chooseProject(shortName: string): { ok: boolean; message: string } {
    if (!this.bytes) return { ok: false, message: 'No schedule file is waiting.' };
    return this.loadXer(this.bytes, this.pendingName || this.fileName || 'schedule.xer', shortName);
  }

  summary(): ScheduleSummary | null {
    const s = this.schedule;
    if (!s) return null;
    const byType: Partial<Record<TaskType, number>> = {};
    for (const t of s.tasks) byType[t.type] = (byType[t.type] ?? 0) + 1;
    return {
      project: s.project.shortName,
      ...(s.project.name ? { projectName: s.project.name } : {}),
      ...(s.project.dataDate ? { dataDate: s.project.dataDate } : {}),
      fileName: this.fileName,
      hash: s.sourceHash,
      tasks: s.tasks.length,
      byType,
      wbs: s.wbs.length,
      relations: s.relations.length,
      codeTypes: Object.entries(s.codeTypes).map(([name, v]) => ({ name, values: v.length })),
      udfs: s.udfLabels,
      warnings: s.warnings.length,
    };
  }

  // ------------------------------------------------------------ the configuration

  setConfig(c: FourDConfig): void {
    this.config = c;
    this.plan = null;
    this.changed();
  }

  /** Read a `.4d.json`. The config of the file replaces the current one when it is a config at all. */
  loadConfigText(text: string): ParsedConfig {
    const r = parseConfig(text);
    if (r.config) {
      this.config = r.config;
      if (this.schedule && !r.config.schedule.project) this.config.schedule.project = this.schedule.project.shortName;
      this.plan = null;
      this.refreshReport();
      this.changed();
    }
    return r;
  }

  exportConfigText(): string { return serializeConfig(this.config); }

  /** Mark activities as not in the model (or clear the mark): kept with the configuration, no coverage gap, named in the film. */
  markNotModelled(codes: readonly string[], on: boolean): void {
    this.config = setNotModelled(this.config, codes, on);
    this.plan = null;
    this.refreshReport();
    this.changed();
  }

  setStyle(patch: Partial<FourDStyle>): void { this.setConfig(setStyle(this.config, patch)); }

  // ------------------------------------------------------------ linking

  /** IfcTask assignments already in the model's IFC files (e.g. written by `xray-4d link --write-ifc`): GlobalId -> task codes. */
  native: Map<string, string[]> | null = null;

  private async readNative(token: number): Promise<void> {
    const loaded = this.app.loaded;
    const srcs = loaded ? sourcesOf.get(loaded) ?? [] : [];
    if (!loaded || !srcs.length) return;
    const out = new Map<string, string[]>();
    try {
      for (const src of srcs) {
        const ids = new Map<number, string>();
        for (const e of loaded.model.elements) if (e.expressId !== undefined && (e.file === src.fileName || (srcs.length === 1 && e.file === undefined))) ids.set(e.expressId, e.globalId);
        const text = new TextDecoder('latin1').decode(new Uint8Array(await src.blob.arrayBuffer()));
        for (const [g, codes] of readNativeTasks(text, ids).native) out.set(g, [...(out.get(g) ?? []), ...codes]);
      }
    } catch { return; }
    if (token === this.token && out.size) { this.native = out; this.emit(); }
  }

  /** Run the linker with the accepted assignments of the mapping tool and the decisions made earlier. */
  link(): LinkSummary | { error: string } {
    const schedule = this.schedule;
    const model = this.fourDModel();
    if (!schedule) return { error: 'Open a schedule (.xer) first.' };
    if (!model) return { error: 'Open a model first.' };
    const warnings: string[] = [];
    this.links = linkSchedule(schedule, model, this.config, this.map.assignments, {
      priorLinks: decisionLinks(this.links), idProperty: ACTIVITY_IDS_PROPERTY, ...(this.native ? { native: this.native } : {}), createdAt: new Date().toISOString(), scheduleFileName: this.fileName, modelFileName: model.name, onWarning: (m) => warnings.push(m),
    });
    this.plan = null;
    this.refreshReport();
    this.changed();
    return this.linkSummary()!;
  }

  private refreshReport(): void {
    const model = this.fourDModel();
    this.report = this.schedule && this.links && model ? buildReport(this.schedule, this.links, model, { config: this.config, maxIds: 2000 }) : null;
  }

  linkSummary(): LinkSummary | null {
    const r = this.report;
    if (!r || !this.links) return null;
    const n = countLinks(this.links);
    const e = r.coverage.elements;
    return {
      elements: { considered: e.considered, linked: e.linked, tied: e.tied, unlinked: e.unlinked, ratio: e.byCount },
      activities: { ...r.coverage.activities },
      ties: r.ties.length,
      proposed: n.proposed, accepted: n.accepted, rejected: n.rejected,
    };
  }

  /** Accept, reject or reopen one link. The decision is kept when the linker runs again. */
  decide(id: string, status: ReviewStatus): boolean {
    if (!this.links) return false;
    const next = decideLink(this.links, id, status);
    if (next === this.links) return false;
    this.links = next;
    this.plan = null;
    this.refreshReport();
    this.changed();
    return true;
  }

  decideAll(ids: readonly string[], status: ReviewStatus): number {
    let n = 0;
    for (const id of ids) if (this.links && this.decideQuiet(id, status)) n++;
    if (n) { this.plan = null; this.refreshReport(); this.changed(); }
    return n;
  }

  private decideQuiet(id: string, status: ReviewStatus): boolean {
    if (!this.links) return false;
    const next = decideLink(this.links, id, status);
    if (next === this.links) return false;
    this.links = next;
    return true;
  }

  /** Select the elements no accepted link builds. */
  selectUnlinked(): number {
    const m = this.app.controller.model;
    const ids = (this.links?.unlinked_elements ?? []).map((g) => m.byGlobalId.get(g)).filter((i): i is number => i !== undefined);
    this.app.selectIds(ids);
    return ids.length;
  }

  /** Select the elements of one group of the unlinked list (the group's query) or the elements of a link. */
  selectGlobalIds(globalIds: readonly string[]): number {
    const m = this.app.controller.model;
    const ids = globalIds.map((g) => m.byGlobalId.get(g)).filter((i): i is number => i !== undefined);
    this.app.selectIds(ids);
    return ids.length;
  }

  selectQuery(query: string): number {
    const m = this.app.controller.model;
    const r = runQuery(m, query);
    if (r.error) return 0;
    this.app.selectIds(r.ids);
    return r.ids.length;
  }

  reportHtml(): string | null { return this.report ? renderReportHtml(this.report) : null; }

  /** The report in a new window (a blob page). Returns false when the browser blocks the window. */
  openReport(): boolean {
    const html = this.reportHtml();
    if (!html) return false;
    const url = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
    const w = window.open(url, '_blank', 'noopener');
    setTimeout(() => URL.revokeObjectURL(url), 60000);
    return !!w;
  }

  exportLinksText(): string | null { return this.links ? serializeLinks(this.links) : null; }

  /** Read a LinkDataset with links: its links become the links of this model (reviewed ones are kept as decisions); its assignments go to the mapping tool. */
  importLinksText(text: string): { links: number; assignments: number; problems: string[]; otherSchedule: boolean } {
    const p = parseLinks(text);
    if (!p.dataset) return { links: 0, assignments: 0, problems: p.problems, otherSchedule: false };
    let assignments = 0;
    if (p.dataset.assignments?.length) assignments = this.map.importJson(text).read;
    const otherSchedule = !!(this.schedule && p.dataset.schedule && p.dataset.schedule.source_hash !== this.schedule.sourceHash);
    this.links = p.dataset;
    this.plan = null;
    this.refreshReport();
    this.changed();
    return { links: p.dataset.links?.length ?? 0, assignments, problems: p.problems, otherSchedule };
  }

  /** GlobalId -> comma-separated task codes of the accepted build links: `Xray_4D.ActivityIds` in the saved IFC. */
  activityIds(): Map<string, string> { return activityIdsMap(this.links?.links); }

  /** The IfcWorkSchedule to write into one IFC file (the same entities `xray-4d link --write-ifc` writes): tasks of the accepted links
   *  with the plan's view dates (or the planned dates), their elements and logic. `expressIds`: GlobalId -> express id in that file. */
  workSchedule(expressIds: ReadonlyMap<string, number>): WorkScheduleSave | null {
    if (!this.schedule || !this.links) return null;
    return buildWorkSchedule({ schedule: this.schedule, links: this.links, expressIds, plan: this.plan ?? undefined, view: this.config.style.view }).save;
  }

  acceptedLinks(): ActivityLink[] { return (this.links?.links ?? []).filter((l) => l.status === 'accepted'); }

  // ------------------------------------------------------------ the plan

  /** Trade colours: the ones of the file's style, then the mapping tool's colour of the (mapped) trade value. */
  tradeColours(): Record<string, string> {
    const out: Record<string, string> = {};
    const schedule = this.schedule;
    if (!schedule) return { ...this.config.style.colours };
    const known = new Set(this.map.valueList('trade').map((v) => v.name));
    const table = this.config.values?.trade ?? {};
    for (const t of schedule.tasks) {
      const raw = readTaskAttr(t, this.config.schedule.trade);
      if (!raw) continue;
      const mapped = table[raw] ?? raw;
      if (known.has(mapped)) out[raw] = colourOf(this.map.values, 'trade', mapped);
      else if (known.has(raw)) out[raw] = colourOf(this.map.values, 'trade', raw);
    }
    return { ...out, ...this.config.style.colours };
  }

  /** Build the plan from the accepted links and the style, and register it under the model's plan name. */
  buildPlan(): FourDPlan | { error: string } {
    const schedule = this.schedule;
    const model = this.fourDModel();
    if (!schedule) return { error: 'Open a schedule (.xer) first.' };
    if (!model) return { error: 'Open a model first.' };
    if (!this.links) { const r = this.link(); if ('error' in r) return r; }
    if (!this.links!.links?.some((l) => l.status === 'accepted')) return { error: 'No link is accepted yet. Link the schedule and accept links first.' };
    const style: FourDStyle = { ...this.config.style, colours: this.tradeColours() };
    const plan = buildPlan(schedule, this.links!, model, style, { config: this.config });
    registerPlan(planName(this.app.modelName), plan);
    this.plan = plan;
    this.playDur = Math.max(0.5, mapSpan(plan));
    this.emit();
    return plan;
  }

  get planKey(): string { return planName(this.app.modelName); }
  get duration(): number { return this.playDur; }

  // ------------------------------------------------------------ play, scrub, record

  /** The score of the plan: a schedule4d cue over the plan's film length, plus the cues of the director when the style asks for one. */
  async score(): Promise<Score | { error: string }> {
    const p = this.plan ?? this.buildPlan();
    if ('error' in p) return p;
    const plan = p;
    this.note = '';
    let extra: Cue[] = [];
    if (plan.style.camera === 'director') {
      const model = this.fourDModel()!;
      const r = await direct(plan, model);
      extra = r.cues;
      this.note = r.note;
    }
    this.playDur = Math.max(0.5, mapSpan(plan));
    const score = makeFourDScore({ name: planName(this.app.modelName) }, this.playDur, extra);
    this.lastScore = score;
    this.emit();
    return score;
  }

  async play(from?: number): Promise<PlayResult> {
    const score = await this.score();
    if ('error' in score) return { ok: false, message: score.error };
    const player = getScorePlayer();
    if (!player) return { ok: false, message: 'The score player is not available.' };
    const ok = player.play(score, { ...(from !== undefined ? { from } : {}), onEnd: () => this.emit() });
    this.emit();
    return ok ? { ok: true, message: this.note || `Playing ${Math.round(this.playDur)} seconds.` } : { ok: false, message: 'The player could not start.' };
  }

  /**
   * The film as script text: the plan as Play builds it, the camera director run as Play runs it, the plan registered under the
   * returned name (the `schedule "Name"` of the script resolves against it).
   */
  async filmScript(): Promise<{ ok: true; name: string; text: string; lines: number; note: string } | { ok: false; message: string }> {
    const p = this.plan ?? this.buildPlan();
    if ('error' in p) return { ok: false, message: p.error };
    let directed: FilmDirected | null = null;
    let why = '';
    if (p.style.camera === 'director') {
      const r = await direct(p, this.fourDModel()!);
      if (r.cues.length > 0 || (r.notes?.length ?? 0) > 0) directed = { cues: r.cues, notes: r.notes ?? [], noteTimes: r.noteTimes ?? [] };
      else why = r.note || 'the director found nothing to do.';
    } else why = `the camera style is "${p.style.camera}", not the director.`;
    const name = filmName(this.schedule?.project.name, this.schedule?.project.shortName, this.fileName);
    registerPlan(name, p);
    const out = filmScript(p, name, directed, why);
    return { ok: true, name, text: out.text, lines: out.lines, note: directed ? '' : `The camera stays put${why ? `: ${why}` : '.'}` };
  }

  /** Open the film as a script in the Script tab (unsaved, under the film's name). */
  async openAsScript(): Promise<PlayResult & { name?: string; lines?: number }> {
    const r = await this.filmScript();
    if (!r.ok) return { ok: false, message: r.message };
    this.stopPlay();
    const status = `Script made from the 4D film: ${r.lines} lines. Press Run.${r.note ? ` ${r.note}` : ''}`;
    if (!window.__xrayScript?.openGenerated(r.text, r.name, status)) return { ok: false, message: 'The Script tab is not available in this build.' };
    return { ok: true, message: status, name: r.name, lines: r.lines };
  }

  pause(): void { const p = getScorePlayer(); if (p?.playing) { if (p.paused) p.resume(); else p.pause(); this.emit(); } }
  stopPlay(): void { const p = getScorePlayer(); if (p?.playing && this.lastScore) p.stop(); this.emit(); }
  get playing(): boolean { return getScorePlayer()?.playing === true && this.lastScore !== null; }
  get paused(): boolean { return getScorePlayer()?.paused === true; }
  /** Seconds into the film. */
  get time(): number { return getScorePlayer()?.time ?? 0; }

  /** The schedule date (plan time, ms) the film shows now. */
  currentPlanMs(): number | null {
    const plan = this.plan;
    if (!plan) return null;
    return planTimeAt(plan, this.playDur > 0 ? this.time / this.playDur : 0);
  }

  /** Jump to a schedule date (plan time, ms). While a film plays it seeks; otherwise it starts the film there and pauses. */
  async seekDate(planMs: number): Promise<boolean> {
    const plan = this.plan ?? (() => { const p = this.buildPlan(); return 'error' in p ? null : p; })();
    if (!plan) return false;
    const t = secondsAtPlan(plan, planMs) * (this.playDur / Math.max(1e-9, mapSpan(plan)));
    const p = getScorePlayer();
    if (!p) return false;
    if (p.playing && this.lastScore) { p.seek(t); return true; }
    const r = await this.play(t);
    if (r.ok) p.pause();
    return r.ok;
  }

  /** Open the video export dialog for this film. */
  async record(): Promise<PlayResult> {
    const rec = window.__xrayRecord;
    if (!rec) return { ok: false, message: 'Video export is not available in this build.' };
    const score = await this.score();
    if ('error' in score) return { ok: false, message: score.error };
    const res = await rec.dialog('4D schedule', score, `${this.app.modelName}-4d`);
    return res ? { ok: res.ok, message: res.message } : { ok: true, message: 'Export cancelled.' };
  }

  formatDate(ms: number): string { return formatDate(ms); }

  // ------------------------------------------------------------ persistence

  private changed(): void {
    this.schedulePersist();
    this.emit();
  }

  private schedulePersist(): void {
    if (this.saveTimer) clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(() => { this.saveTimer = null; void this.flush(); }, 400);
  }

  /** Write the record now. */
  async flush(): Promise<boolean> {
    if (this.saveTimer) { clearTimeout(this.saveTimer); this.saveTimer = null; }
    if (!this.key) return false;
    const s = this.schedule;
    const bytes = this.bytes && this.bytes.byteLength <= MAX_STORED_XER ? this.bytes.slice().buffer as ArrayBuffer : undefined;
    const rec: ScheduleRecord = {
      schema: 'xray-4d-schedule/1', key: this.key, saved: new Date().toISOString(), config: this.config, links: this.links,
      file: s ? { name: this.fileName, hash: s.sourceHash, project: s.project.shortName, ...(bytes ? { bytes } : {}) } : null,
    };
    return this.store.put(rec);
  }

  /** Forget the schedule, the links and the config of this model (the stored record too). */
  reset(): void {
    this.schedule = null; this.bytes = null; this.fileName = ''; this.links = null; this.report = null; this.plan = null; this.pendingProjects = null;
    this.config = emptyConfig();
    this.stopPlay();
    this.changed();
  }

  // ------------------------------------------------------------ the sample

  /** FZK-Haus 4D: the sample schedule and configuration from /samples (or the bundle), linked, ready to play. */
  async loadSample(): Promise<PlayResult> {
    if (this.app.modelName !== SAMPLE_4D_MODEL) await this.app.loadScene(SAMPLE_4D_MODEL);
    await this.ready();
    await this.map.ready();
    const { SAMPLE_XER, SAMPLE_CONFIG } = await import('./sampleFiles');
    const r = this.loadXer(SAMPLE_XER, 'fzk-haus.xer');
    if (!r.ok) return r;
    const c = this.loadConfigText(SAMPLE_CONFIG);
    if (!c.config) return { ok: false, message: c.problems[0] ?? 'The sample configuration is not valid.' };
    const l = this.link();
    if ('error' in l) return { ok: false, message: l.error };
    const p = this.buildPlan();
    if ('error' in p) return { ok: false, message: p.error };
    return { ok: true, message: `FZK-Haus 4D: ${l.elements.linked} of ${l.elements.considered} elements linked.` };
  }
}
