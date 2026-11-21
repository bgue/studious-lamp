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
import type { PanelHandle } from '../map4d/panel';
import type { Target } from '../map4d/targets';
import type { Assignment, AttributeKind } from '../schedule/types';
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

declare global {
  interface Window {
    __xray4dMap?: Map4dApi;
  }
}

export const map4dPlugin: AppPlugin = (() => {
  let ctl: Map4dController | null = null;
  let tab: RightTabHandle | null = null;
  let panel: PanelHandle | null = null;
  return {
    name: 'map4d',
    install(app) {
      const c = new Map4dController(app);
      ctl = c;
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
      tab = addRightSidebarTab({
        id: '4d',
        label: '4D',
        order: 50,
        width: 420,
        title: 'Assign a location, trade and zone to elements so a schedule can be linked to the model',
        helpKey: 'Right sidebar/4D tab',
        mount(pane, ctx) {
          panel = buildMapPanel(pane, app, c, ctx);
          return () => { panel?.dispose(); panel = null; };
        },
      });
      registerAction({
        id: 'map4d.open', label: '4D mapping: open the 4D tab', group: 'Tools', keys: [],
        description: 'Assign location, trade and zone to elements for the 4D schedule link',
        run: () => tab?.show(),
      });
    },
    onModel() { ctl?.onModel(); panel?.render(); },
  };
})();
