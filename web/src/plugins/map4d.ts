// 4D mapping tool: assign a Location, Trade and Zone to IFC elements, review suggestions, check coverage, and save the result into the IFC
// (property set Xray_4D) so a P6 schedule can be linked by those attributes. Design: docs/design/4d-xer-animation.md sections 3 and 10;
// the data model is the LinkML schema schema/linkml/xray_4d.yaml (`Assignment`). Logic in src/map4d, the panel in src/map4d/panel.ts.
//
//   window.__xray4dMap = { values(), assign(attr, value, target), clear(attr, target), suggest(), proposals(), accept(ids), reject(ids),
//                          coverage(), colourBy(attr|null), selectUnassigned(attr), exportJson(), importJson(text), saveMap(),
//                          assignments(), ready(), flush(), reset(), open() }
//   target: { selection: true } | { query } | { storey: name|id } | { set: name } | { ids: number[] } | { globalIds: string[] }
//   Right sidebar tab "4D" (order 50, width 420). Assignments persist per model in IndexedDB; Save IFC writes them (src/ifcsave).

import type { AppPlugin } from '../app';
import { registerAction } from '../input/actions';
import { Map4dController } from '../map4d/controller';
import type { Coverage, SuggestSummary } from '../map4d/controller';
import type { ElementValues } from '../map4d/assignments';
import type { ImportOutcome } from '../map4d/linkio';
import { buildMapPanel } from '../map4d/panel';
import { ScheduleController } from '../map4d/scheduleController';
import type { LinkSummary, PlayResult, ScheduleSummary } from '../map4d/scheduleController';
import type { ParsedConfig } from '../map4d/scheduleConfig';
import type { PanelHandle } from '../map4d/panel';
import type { Target } from '../map4d/targets';
import type { Assignment, AttributeKind, FourDConfig, FourDLinks, FourDPlan, ReviewStatus } from '../schedule/types';
import type { LinkReport } from '../schedule/report';
import { getTempWorksLayer } from '../anim/fourd/tempWorksLayer';
import type { TempWorksLayer } from '../anim/fourd/tempWorksLayer';
import { addRightSidebarTab } from './rightSidebar';
import type { RightTabHandle } from './rightSidebar';

export interface Map4dApi {
  values(): Record<AttributeKind, string[]>;
  assign(attr: AttributeKind, value: string, target: Target): { assigned: number; unchanged: number; matched: number; error?: string };
  clear(attr: AttributeKind, target: Target): number;
  suggest(attributes?: AttributeKind[]): SuggestSummary;
  proposals(): Assignment[];
  accept(ids: string[]): number;
  reject(ids: string[]): number;
  acceptAbove(limit: number, attr?: AttributeKind): number;
  coverage(): Coverage;
  colourBy(attr: AttributeKind | null): AttributeKind | null;
  selectUnassigned(attr: AttributeKind): number;
  exportJson(opts?: { includeReviewers?: boolean }): string;
  importJson(text: string): ImportOutcome;
  /** Accepted values by GlobalId: what Save IFC writes as Xray_4D. */
  saveMap(): Map<string, ElementValues>;
  assignments(): Assignment[];
  /** Resolves when the stored record of the model on screen has been read and Xray_4D read back. */
  ready(): Promise<void>;
  flush(): Promise<boolean>;
  reset(): void;
  open(): void;
}

/** window.__xray4dSchedule: the schedule workflow of the 4D tab (src/map4d/scheduleController.ts), for scripts and smoke tests. */
export interface Schedule4dApi {
  /** Read an XER file (text, or bytes). A file with several projects waits for chooseProject (summary().pendingProjects). */
  load(input: string | Uint8Array, name?: string, project?: string): { ok: boolean; message: string };
  chooseProject(shortName: string): { ok: boolean; message: string };
  /** The schedule's summary, or null; `pendingProjects` lists the projects of a file that waits for a choice. */
  summary(): (ScheduleSummary & { pendingProjects?: string[] }) | { pendingProjects: string[] } | null;
  config(): FourDConfig;
  setConfig(c: FourDConfig): void;
  loadConfig(text: string): ParsedConfig;
  exportConfig(): string;
  /** Run the linker with the accepted assignments of the mapping tool and the earlier decisions. */
  link(): LinkSummary | { error: string };
  links(): FourDLinks | null;
  report(): LinkReport | null;
  reportHtml(): string | null;
  decide(linkId: string, status: ReviewStatus): boolean;
  exportLinks(): string | null;
  importLinks(text: string): { links: number; assignments: number; problems: string[]; otherSchedule: boolean };
  /** Build the plan (registered as plan name `4d:<model>`). */
  plan(): FourDPlan | { error: string };
  play(from?: number): Promise<PlayResult>;
  stop(): void;
  /** Jump to a schedule date (plan time, ms). */
  seekDate(planMs: number): Promise<boolean>;
  record(): Promise<PlayResult>;
  /** Make the film a script: build the plan as Play does, run the camera director, register the plan by the schedule's name and open the Script tab with the text (unsaved). */
  openAsScript(): Promise<PlayResult & { name?: string; lines?: number }>;
  /** GlobalId -> comma-separated task codes of the accepted build links (what Save IFC writes as Xray_4D.ActivityIds). */
  activityIds(): ReadonlyMap<string, string>;
  /** The IfcWorkSchedule for one IFC file (GlobalId -> express id of that file), or null without a schedule and links. */
  workSchedule(expressIds: ReadonlyMap<string, number>): import('../ifcsave/workSchedule').WorkScheduleSave | null;
  /** FZK-Haus 4D: load the model, the sample schedule and configuration, link, build the plan. */
  loadSample(): Promise<PlayResult>;
  /** Open the 4D tab and a section of it (schedule, configure, link, style, play): the section opens when collapsed and scrolls into view; play scrolls to the film bar at the top. */
  open(section?: string): void;
  /** Show a step of the tab (map, link or film) without opening a section; no argument: the step now shown. Null while the tab is not built. */
  step(id?: 'map' | 'link' | 'film'): 'map' | 'link' | 'film' | null;
  /** Mark activities as not in the model (or clear the mark): kept with the configuration. */
  markNotModelled(codes: string[], on?: boolean): void;
  /** The temporary works layer of the film: its visibility, the groups of the plan, their state now (phase, progress, pieces shown) and the label of the piece under a point (NDC). */
  tempWorks(set?: { visible?: boolean }): { visible: boolean; groups: NonNullable<FourDPlan['temporaryWorks']>['groups']; state: ReturnType<TempWorksLayer['state']>; pick(ndcX: number, ndcY: number): string | null };
  ready(): Promise<void>;
  flush(): Promise<boolean>;
  reset(): void;
  /** True while the film plays. */
  readonly playing: boolean;
  /** The note about what the film cannot do in this build (no director). */
  readonly note: string;
}

declare global {
  interface Window {
    __xray4dSchedule?: Schedule4dApi;
    __xray4dMap?: Map4dApi;
  }
}

export const map4dPlugin: AppPlugin = (() => {
  let ctl: Map4dController | null = null;
  let tab: RightTabHandle | null = null;
  let panel: PanelHandle | null = null;
  let sched: ScheduleController | null = null;
  return {
    name: 'map4d',
    install(app) {
      const c = new Map4dController(app);
      ctl = c;
      const sc = new ScheduleController(app, c);
      sched = sc;
      const api: Map4dApi = {
        values: () => ({ location: c.valueList('location').map((v) => v.name), trade: c.valueList('trade').map((v) => v.name), zone: c.valueList('zone').map((v) => v.name) }),
        assign: (attr, value, target) => c.assign(attr, value, target),
        clear: (attr, target) => c.clearAssignment(attr, target),
        suggest: (attrs) => c.suggest(attrs),
        proposals: () => c.proposals(),
        accept: (ids) => c.accept(ids),
        reject: (ids) => c.reject(ids),
        acceptAbove: (limit, attr) => c.acceptAbove(limit, attr),
        coverage: () => c.coverage(),
        colourBy: (attr) => { c.setColourBy(attr); return c.colourBy; },
        selectUnassigned: (attr) => c.selectUnassigned(attr),
        exportJson: (o) => c.exportJson(o).json,
        importJson: (text) => c.importJson(text),
        saveMap: () => c.saveMap(),
        assignments: () => c.assignments.map((a) => ({ ...a })),
        ready: () => c.ready(),
        flush: () => c.flush(),
        reset: () => c.reset(),
        open: () => tab?.show(),
      };
      window.__xray4dMap = api;
      const open = (id?: string): void => { tab?.show(); if (id) panel?.openSection(id); };
      window.__xray4dSchedule = {
        load: (input, name = 'schedule.xer', project) => sc.loadXer(input, name, project),
        chooseProject: (n) => sc.chooseProject(n),
        summary: () => { const s = sc.summary(); const p = sc.pendingProjects?.map((x) => x.shortName); return s ? { ...s, ...(p ? { pendingProjects: p } : {}) } : p ? { pendingProjects: p } : null; },
        config: () => JSON.parse(JSON.stringify(sc.config)) as FourDConfig,
        setConfig: (cfg) => sc.setConfig(cfg),
        loadConfig: (t) => sc.loadConfigText(t),
        exportConfig: () => sc.exportConfigText(),
        link: () => sc.link(),
        links: () => (sc.links ? (JSON.parse(JSON.stringify(sc.links)) as FourDLinks) : null),
        report: () => sc.report,
        reportHtml: () => sc.reportHtml(),
        decide: (id, status) => sc.decide(id, status),
        exportLinks: () => sc.exportLinksText(),
        importLinks: (t) => sc.importLinksText(t),
        plan: () => sc.buildPlan(),
        play: (from) => sc.play(from),
        stop: () => sc.stopPlay(),
        seekDate: (ms) => sc.seekDate(ms),
        record: () => sc.record(),
        openAsScript: () => sc.openAsScript(),
        activityIds: () => sc.activityIds(),
        workSchedule: (ids) => sc.workSchedule(ids),
        loadSample: async () => { open('play'); const r = await sc.loadSample(); panel?.render(); open('play'); return r; },
        open,
        step: (id) => panel?.showStep(id) ?? null,
        markNotModelled: (codes, on = true) => sc.markNotModelled(codes, on),
        tempWorks: (set) => {
          const l = getTempWorksLayer(app);
          if (set?.visible !== undefined) { l.setVisible(set.visible); panel?.render(); }
          return { visible: l.visible, groups: sc.plan?.temporaryWorks?.groups ?? [], state: l.state(), pick: (x, y) => l.describeAt(x, y) };
        },
        ready: () => sc.ready(),
        flush: () => sc.flush(),
        reset: () => sc.reset(),
        get playing() { return sc.playing; },
        get note() { return sc.note; },
      };
      tab = addRightSidebarTab({
        id: '4d',
        label: '4D',
        order: 50,
        width: 420,
        title: 'Assign a location, trade and zone to elements so a schedule can be linked to the model',
        helpKey: 'Right sidebar/4D tab',
        mount(pane, ctx) {
          panel = buildMapPanel(pane, app, c, sc, ctx);
          return () => { panel?.dispose(); panel = null; };
        },
      });
      registerAction({
        id: 'map4d.open', label: '4D mapping: open the 4D tab', group: 'Tools', keys: [],
        description: 'Assign location, trade and zone to elements for the 4D schedule link',
        run: () => tab?.show(),
      });
    },
    onModel() { ctl?.onModel(); sched?.onModel(); panel?.render(); panel?.repick(); },
  };
})();
