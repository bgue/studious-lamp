// Issues plugin: BCF is the container, the markup drawing engine is the drawing layer. This file wires
//   - the sidebar tab "Issues" with the segments Issues and Sketches (src/issues/ui.ts), and on a phone a bottom sheet,
//   - the drawing toolbar's state (the controller's `editing` flag; the bar itself is src/markup/toolbar.ts, drawn by the view),
//   - "N open issues" in the status bar, which opens the tab,
//   - the palette actions and the aliases of the actions that opened the old BCF and Markup drawers (tool.bcf, tool.markup),
//   - window.__xrayIssues for scripts and the smoke tests.
// The controllers are the ones of the markup and bcf plugins; those install first. Docs: docs-features/issues.md.

import type { AppPlugin, ViewerApp } from '../app';
import { registerAction } from '../input/actions';
import { el } from '../ui/dom';
import { STATUS_H } from '../ui/statusBar';
import { IssuesController } from '../issues/controller';
import type { Segment } from '../issues/controller';
import { buildIssuesPanel } from '../issues/ui';
import type { IssuesPanel } from '../issues/ui';
import type { IssueHit } from '../issues/search';
import type { BcfTopic, BcfViewpointRef } from '../bcf/model';
import type { MarkupSet } from '../markup/model';
import { bcfController } from './bcf';
import { markupController } from './markup';
import { addSidebarTab, collapseSidebar } from './sidebar';
import type { SidebarTabHandle } from './sidebar';

declare global {
  interface Window {
    __xrayIssues?: {
      /** Open the Issues tab (a bottom sheet on a phone) on a segment. */
      open(segment?: Segment): void;
      /** Close the bottom sheet (a phone); on a wide screen the sidebar stays as it is. */
      close(): void;
      readonly segment: Segment;
      /** The open detail: an issue guid or a sketch id. */
      readonly detail: { kind: 'issue' | 'sketch'; id: string } | null;
      /** The panel is on screen: the sidebar tab is shown, or the phone sheet is up. */
      readonly visible: boolean;
      readonly phone: boolean;
      /** A new sketch from the current view, open in the detail with the drawing toolbar up. */
      newSketch(title?: string): MarkupSet;
      /** Show the drawing toolbar for a sketch, or for an issue viewpoint (the sketch of it). */
      editSketch(id: string): boolean;
      editViewpoint(topicGuid: string, viewpointGuid: string): boolean;
      /** The drawing toolbar is up. */
      readonly editing: boolean;
      stopEditing(): void;
      openIssue(guid: string, opts?: { apply?: boolean }): boolean;
      openSketch(id: string): boolean;
      /** Raise a sketch as an issue: a new one, or one more viewpoint of `topic`. Returns the issue guid. */
      raise(setId: string, opts?: { topic?: string }): Promise<string>;
      /** The issue a sketch belongs to (topic and viewpoint guid), or null. */
      issueOf(setId: string): { topic: string; viewpoint: string } | null;
      /** The sketches of an issue, in viewpoint order. */
      sketchesOf(topicGuid: string): MarkupSet[];
      /** Remove a sketch; one that belongs to an issue returns `confirm` until called with `confirmed`. */
      removeSketch(setId: string, confirmed?: boolean): 'removed' | 'confirm' | 'none';
      /** Sketches with comments or a status that the banner offers to raise. */
      legacyCount(): number;
      migrate(): Promise<{ issues: number; failed: number }>;
      readonly openCount: number;
      /** Issues and sketches by title, note and comment text (what the top-bar search lists). */
      search(query: string): IssueHit[];
      hit(kind: 'issue' | 'sketch', id: string): IssueHit | null;
      openHit(hit: Pick<IssueHit, 'kind' | 'id'>): boolean;
      /** The sketch is tied to a 3D construct, so it has the 3D · Plan · Section switch. */
      viewSwitchAvailable(setId: string): boolean;
      /** The live view of a sketch: `3d` unless Plan or Section was chosen for it. */
      viewMode(setId: string): '3d' | 'plan' | 'section';
      /** Switch the live view of a sketch (the buttons of the switch do this). False when it cannot. */
      setViewMode(setId: string, mode: '3d' | 'plan' | 'section'): boolean;
      /** The derived Plan or Section of a sketch as it would be set now (camera, clip planes), or null. */
      derivedView(setId: string, mode: 'plan' | 'section'): import('../issues/derivedViews').DerivedView | null;
      /** Rebuild the drawings of the issue viewpoints from their sketches now (export does it too). */
      sync(): number;
      setStatusFilter(f: 'all' | 'open' | 'closed'): void;
      setQuery(q: string): void;
      readonly controller: IssuesController;
    };
  }
}

const PHONE_QUERY = '(max-width: 700px)';

const SHEET_CSS = `
#issues-sheet{position:absolute;left:var(--sb-rail,28px);right:var(--dk-rail,28px);bottom:${STATUS_H}px;max-height:68%;z-index:16;box-sizing:border-box;display:none;flex-direction:column;background:rgba(20,24,32,.98);color:var(--sb-fg,#dfe6ee);border:1px solid #2d3748;border-bottom:0;border-radius:10px 10px 0 0;font:13px/1.35 system-ui,-apple-system,'Segoe UI',sans-serif;box-shadow:0 -6px 24px rgba(0,0,0,.45)}
#issues-sheet.on{display:flex}
#issues-sheet .is-sheet-head{display:flex;align-items:center;gap:8px;padding:6px 8px;border-bottom:1px solid var(--sb-line,#262d3a);flex:0 0 auto}
#issues-sheet .is-sheet-grip{width:36px;height:4px;border-radius:2px;background:#4a5568;margin:0 auto}
#issues-sheet .is-sheet-title{flex:1;font-weight:700}
#issues-sheet .is-sheet-x{background:transparent;border:1px solid var(--sb-line,#262d3a);color:inherit;border-radius:6px;min-width:34px;min-height:30px;font:inherit;cursor:pointer}
#issues-sheet .is-sheet-body{flex:1 1 auto;min-height:0;display:flex;flex-direction:column;overflow:hidden}
#xray-overlay .xs-issues{flex:0 0 auto;padding:0 8px;background:transparent;border:0;border-left:1px solid var(--sb-line,#262d3a);color:inherit;font:inherit;line-height:inherit;cursor:pointer;white-space:nowrap}
#xray-overlay .xs-issues:hover{background:var(--sb-hover,#1c2230)}
#xray-overlay .xs-issues.has{color:#ffd37a}
`;

let ctl: IssuesController | null = null;
let poll: (() => void) | null = null;

export const issuesPlugin: AppPlugin = {
  name: 'issues',

  install(app: ViewerApp): void {
    const mk = markupController();
    const bcf = bcfController();
    if (!mk || !bcf) return;
    const c = new IssuesController(app, mk, bcf);
    ctl = c;
    const stage = app.canvas.parentElement ?? document.body;
    if (!document.getElementById('issues-sheet-style')) {
      const st = document.createElement('style');
      st.id = 'issues-sheet-style';
      st.textContent = SHEET_CSS;
      document.head.appendChild(st);
    }

    // ---- the panel: in the sidebar tab, or in the bottom sheet on a phone
    const pane = el('div', 'issues-pane');
    pane.style.cssText = 'display:flex;flex-direction:column;min-height:0;flex:1 1 auto';
    const panel: IssuesPanel = buildIssuesPanel(pane, c);
    const sheet = el('div', '', { id: 'issues-sheet', role: 'dialog', 'aria-label': 'Issues and sketches', 'data-help-key': 'Issues panel/Phone sheet' });
    const head = el('div', 'is-sheet-head');
    const grip = el('div', 'is-sheet-grip');
    const title = el('div', 'is-sheet-title', undefined, 'Issues');
    const close = el('button', 'is-sheet-x', { type: 'button', 'aria-label': 'Close the issues sheet', title: 'Close', 'data-act': 'sheet-close' }, '×');
    head.append(title, close);
    const body = el('div', 'is-sheet-body');
    sheet.append(grip, head, body);
    stage.appendChild(sheet);

    const mq = window.matchMedia ? window.matchMedia(PHONE_QUERY) : null;
    const phone = (): boolean => !!mq?.matches;
    let sheetWanted = false; // the user opened the sheet (a phone)
    let wasShown = false;
    let tab: SidebarTabHandle | null = null;

    const place = (): void => {
      // The panel root sits in the sheet on a phone and in the sidebar pane otherwise.
      const inSheet = phone();
      const want = inSheet ? body : pane;
      if (panel.root.parentElement !== want) want.appendChild(panel.root);
      const show = inSheet && sheetWanted && !(mk.editing && mk.active);
      sheet.classList.toggle('on', show);
      title.textContent = c.segment === 'issues' ? 'Issues' : c.segment === 'sheets' ? 'Sheets' : 'Sketches';
    };
    const visible = (): boolean => (phone() ? sheet.classList.contains('on') : !!tab?.visible());
    const syncOpen = (): void => {
      const v = visible();
      if (v !== wasShown) {
        wasShown = v;
        bcf.setDrawerOpen(v); // pins show while the panel is up
        if (v) panel.render();
      }
    };

    poll = syncOpen;
    tab = addSidebarTab({
      id: 'issues',
      label: 'Issues',
      pane,
      helpKey: 'Sidebar/Issues tab',
      onShow: () => {
        if (phone()) {
          sheetWanted = true;
          collapseSidebar();
        }
        place();
        syncOpen();
        panel.render();
      },
    });
    close.addEventListener('click', () => {
      sheetWanted = false;
      place();
      syncOpen();
    });
    mq?.addEventListener?.('change', () => { place(); syncOpen(); });

    c.onChange(() => {
      place();
      updateStatus();
      syncOpen();
    });

    // ---- the status bar: "N open issues", opens the tab on the open issues
    const bar = app.status.root;
    const chip = el('button', 'xs-issues', { type: 'button', 'data-help-key': 'Status bar/Open issues', 'data-act': 'open-issues', 'aria-label': 'Open issues' });
    const anchor = bar.querySelector('.xs-elem');
    if (anchor) bar.insertBefore(chip, anchor);
    else bar.appendChild(chip);
    function updateStatus(): void {
      const n = c.openCount();
      const text = `${n} open issue${n === 1 ? '' : 's'}`;
      if (chip.textContent !== text) chip.textContent = text;
      chip.classList.toggle('has', n > 0);
      chip.title = n ? `${text}: open the Issues tab` : 'No open issues: open the Issues tab';
    }
    chip.addEventListener('click', () => {
      c.statusFilter = 'open';
      api.open('issues');
    });
    updateStatus();

    // ---- scripting
    const api: NonNullable<Window['__xrayIssues']> = {
      open(segment) {
        if (segment) c.setSegment(segment);
        if (phone()) sheetWanted = true;
        if (tab) tab.show();
        else if (phone()) sheetWanted = true;
        if (phone()) collapseSidebar();
        place();
        syncOpen();
        panel.render();
      },
      close() {
        sheetWanted = false;
        place();
        syncOpen();
      },
      get segment() {
        return c.segment;
      },
      get detail() {
        return c.detail ? { ...c.detail } : null;
      },
      get visible() {
        return visible();
      },
      get phone() {
        return phone();
      },
      newSketch(t) {
        api.open('sketches');
        return c.newSketch(t);
      },
      editSketch: (id) => c.editSketch(id),
      editViewpoint(topicGuid, viewpointGuid) {
        const t: BcfTopic | undefined = bcf.topic(topicGuid);
        const v: BcfViewpointRef | undefined = t?.viewpoints.find((x) => x.guid === viewpointGuid);
        return !!t && !!v && c.editViewpoint(t, v);
      },
      get editing() {
        return mk.editing;
      },
      stopEditing: () => mk.setEditing(false),
      openIssue: (g, o) => c.openIssue(g, o),
      openSketch: (id) => c.openSketch(id),
      raise: (id, o) => c.raise(id, o),
      issueOf: (id) => {
        const r = c.issueOf(id);
        return r ? { topic: r.topic.guid, viewpoint: r.viewpoint.guid } : null;
      },
      sketchesOf: (g) => {
        const t = bcf.topic(g);
        return t ? c.sketchesOf(t) : [];
      },
      removeSketch: (id, confirmed) => c.removeSketch(id, confirmed === true),
      legacyCount: () => c.legacy().length,
      migrate: () => c.migrateLegacy(),
      get openCount() {
        return c.openCount();
      },
      search: (q) => c.search(q),
      hit: (k, id) => c.hitOf(k, id),
      openHit: (h) => {
        const ok = c.openHit(h);
        if (ok) api.open(h.kind === 'issue' ? 'issues' : 'sketches');
        return ok;
      },
      viewSwitchAvailable: (id) => c.views.tied(mk.get(id)),
      viewMode: (id) => c.views.mode(mk.get(id)),
      setViewMode: (id, mode) => c.views.apply(id, mode),
      derivedView: (id, mode) => { const set = mk.get(id); return set ? c.views.derive(set, mode) : null; },
      sync: () => c.syncAll(),
      setStatusFilter: (f) => {
        c.statusFilter = f;
        c.emit();
      },
      setQuery: (q) => {
        c.query = q;
        c.emit();
      },
      get controller() {
        return c;
      },
    };
    window.__xrayIssues = api;

    // ---- actions: the new ones, and the ids that opened the old drawers
    registerAction({ id: 'issues.open', label: 'Issues: open the tab', group: 'Panels', keys: [], description: 'Open the Issues tab on the Issues segment', run: () => api.open('issues') });
    registerAction({ id: 'issues.sketches', label: 'Issues: open the Sketches segment', group: 'Panels', keys: [], description: 'Open the Issues tab on the Sketches segment', run: () => api.open('sketches') });
    registerAction({ id: 'issues.edit', label: 'Sketches: edit the drawing', group: 'Markup', keys: [], description: 'Show the drawing toolbar for the active sketch', run: () => { const s = mk.active; if (s) c.editSketch(s.id); } });
    registerAction({ id: 'issues.done', label: 'Sketches: finish drawing', group: 'Markup', keys: [], description: 'Hide the drawing toolbar', run: () => mk.setEditing(false) });
    registerAction({ id: 'tool.bcf', label: 'Tool: BCF', group: 'Panels', keys: [], description: 'Open the Issues tab (formerly the BCF drawer)', run: () => api.open('issues') });
    registerAction({ id: 'tool.markup', label: 'Tool: Markup', group: 'Panels', keys: [], description: 'Open the Issues tab on the Sketches segment (formerly the Markup drawer)', run: () => api.open('sketches') });
  },

  onModel(): void {
    ctl?.onModel();
  },

  afterFrame(): void {
    // The sidebar tab can be left by the user without a callback: keep the pins in step with what is on screen.
    poll?.();
  },
};
