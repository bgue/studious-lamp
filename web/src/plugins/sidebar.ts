// Sidebar plugin: collapsible left panel with a model tree ("Model"), selection sets ("Sets") and a properties footer.
//
// Layout lives in index.html (#app > #sidebar + #stage > canvas). This module fills #sidebar, owns its state
// (collapsed flag and active tab, persisted in localStorage under `xray.sidebar`) and keeps the renderer sized.
//
// Visibility (eye icon): there is no controller method that takes an id list, so the tree edits
// controller.settings.overrides.userHides directly (the same set hideSelected() writes; ids being hidden are also
// removed from userPins, as hideSelected() does), then calls controller.refreshOverrides() (Algorithm 7) and
// app.runSightlinesNow() (applies hidden flags and reruns Algorithm 2). This avoids touching the selection.

import type { AppPlugin, ViewerApp } from '../app';
import type { ElementId } from '../types';
import { MemoryStorage } from '../selectionSets';
import type { StorageLike } from '../selectionSets';
import { unionBounds } from '../selectionSets';
import { PropsView } from '../ui/propsView';
import type { PropsData } from '../ui/propsView';
import { SetsView } from '../ui/setsView';
import { TreeView } from '../ui/treeView';
import { boxFromTuple, requestFrame } from '../ui/fit';
import { debounce, el } from '../ui/dom';
import { registerAction } from '../input/actions';

const STATE_KEY = 'xray.sidebar';
const REFRESH_MS = 250;

type Tab = 'model' | 'sets';
interface SidebarState {
  collapsed: boolean;
  tab: Tab;
}

function storage(): StorageLike {
  try {
    const s = window.localStorage;
    s.getItem('xray.probe');
    return s;
  } catch {
    return new MemoryStorage();
  }
}

function sameIds(a: readonly ElementId[], b: readonly ElementId[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

interface Ui {
  app: ViewerApp;
  sidebar: HTMLElement;
  toggle: HTMLButtonElement;
  tabs: Record<Tab, HTMLButtonElement>;
  panes: Record<Tab, HTMLElement>;
  filter: HTMLInputElement;
  filterInfo: HTMLElement;
  tree: TreeView;
  sets: SetsView;
  props: PropsView;
  store: StorageLike;
  state: SidebarState;
  lastSelection: ElementId[];
  fromUi: boolean;
  lastRefresh: number;
}

let ui: Ui | null = null;

function readState(store: StorageLike): SidebarState {
  const narrow = window.matchMedia?.('(max-width: 700px)').matches ?? false;
  const def: SidebarState = { collapsed: narrow, tab: 'model' };
  try {
    const v = JSON.parse(store.getItem(STATE_KEY) ?? 'null') as Partial<SidebarState> | null;
    if (v) return { collapsed: typeof v.collapsed === 'boolean' ? v.collapsed : def.collapsed, tab: v.tab === 'sets' ? 'sets' : 'model' };
  } catch {
    /* ignore */
  }
  return def;
}

function saveState(u: Ui): void {
  try {
    u.store.setItem(STATE_KEY, JSON.stringify(u.state));
  } catch {
    /* ignore */
  }
}

function applyState(u: Ui): void {
  document.body.classList.toggle('sb-collapsed', u.state.collapsed);
  u.toggle.setAttribute('aria-expanded', String(!u.state.collapsed));
  u.toggle.title = u.state.collapsed ? 'Expand sidebar ([)' : 'Collapse sidebar ([)';
  u.toggle.textContent = u.state.collapsed ? '›' : '‹';
  for (const t of ['model', 'sets'] as Tab[]) {
    u.tabs[t].classList.toggle('active', u.state.tab === t);
    u.tabs[t].setAttribute('aria-selected', String(u.state.tab === t));
    u.panes[t].style.display = u.state.tab === t ? '' : 'none';
  }
}

function setCollapsed(u: Ui, collapsed: boolean): void {
  u.state.collapsed = collapsed;
  applyState(u);
  saveState(u);
  if (!collapsed) refreshAll(u);
  // The stage resizes with the sidebar; the ResizeObserver on the canvas re-sizes the renderer, and this covers the
  // end of the width transition explicitly.
  window.setTimeout(() => resizeRenderer(u.app), 220);
}

function resizeRenderer(app: ViewerApp): void {
  app.renderer.resize();
  app.renderer.markDirty();
}

function setTab(u: Ui, tab: Tab): void {
  u.state.tab = tab;
  applyState(u);
  saveState(u);
  refreshAll(u);
}

/** Run a selection change that originates in the sidebar (the tree must not re-expand or scroll for it). */
function selectFromUi(u: Ui, ids: ElementId[], additive: boolean): void {
  u.fromUi = true;
  try {
    u.app.selectIds(ids, additive);
  } finally {
    u.fromUi = false;
  }
}

function setHidden(app: ViewerApp, ids: ElementId[], hide: boolean): void {
  const ov = app.controller.settings.overrides;
  for (const id of ids) {
    if (hide) {
      ov.userHides.add(id);
      ov.userPins.delete(id);
    } else ov.userHides.delete(id);
  }
  app.controller.refreshOverrides();
  app.runSightlinesNow();
}

function frameIds(app: ViewerApp, ids: ElementId[]): void {
  const b = unionBounds(app.controller.model, ids);
  if (!b) return;
  requestFrame(app.renderer.camera, app.renderer.controls, boxFromTuple(b));
  // Idempotent when the cinematic plugin took over: it moves the camera, which schedules sightlines itself.
  app.renderer.markDirty();
}

function propsData(app: ViewerApp): PropsData | null {
  const sel = app.selection;
  const id = sel[0];
  if (id === undefined) return null;
  const info = app.controller.describe(id);
  const e = app.controller.model.elements[id];
  if (!info || !e) return null;
  const storey = e.storey === null ? undefined : app.controller.model.storeys.find((s) => s.id === e.storey);
  return {
    globalId: e.globalId,
    ifcClass: info.ifcClass,
    name: info.name ?? '',
    storey: storey ? storey.name : 'No storey',
    material: e.material ?? '',
    bucket: info.bucket,
    proximityWeight: info.proximityWeight,
    occlusion: info.occlusion,
    targetAlpha: info.targetAlpha,
    alpha: info.alpha,
    more: sel.length - 1,
  };
}

function refreshAll(u: Ui): void {
  if (u.state.collapsed || !u.app.loaded) return;
  if (u.state.tab === 'model') u.tree.refresh();
  u.props.update(propsData(u.app));
}

function updateFilterInfo(u: Ui): void {
  u.filterInfo.textContent = u.tree.filtered ? `${u.tree.visibleElementCount()} match${u.tree.visibleElementCount() === 1 ? '' : 'es'}` : '';
}

function buildDom(app: ViewerApp, sidebar: HTMLElement): Ui {
  const store = storage();
  sidebar.textContent = '';

  const top = el('div', 'sb-top');
  const toggle = el('button', 'sb-toggle', { type: 'button', 'aria-controls': 'sb-body' });
  const tabsEl = el('div', 'sb-tabs', { role: 'tablist' });
  const tabs = {
    model: el('button', 'sb-tab', { type: 'button', role: 'tab' }, 'Model'),
    sets: el('button', 'sb-tab', { type: 'button', role: 'tab' }, 'Sets'),
  };
  tabsEl.append(tabs.model, tabs.sets);
  const railLabel = el('div', 'sb-rail-label', {}, 'Model tree');
  top.append(toggle, tabsEl);

  const body = el('div', 'sb-body', { id: 'sb-body' });
  const modelPane = el('div', 'sb-pane');
  const filterRow = el('div', 'sb-filter');
  const filter = el('input', 'inp', { type: 'search', placeholder: 'Filter by name, GlobalId or class', 'aria-label': 'Filter model tree' });
  const filterInfo = el('span', 'sb-filter-info');
  filterRow.append(filter, filterInfo);

  const tree = new TreeView({
    selection: () => app.controller.selection,
    bucketOf: (id) => app.controller.bucketOf(id),
    hidden: () => app.controller.settings.overrides.userHides,
    select: (ids, additive) => selectFromUi(ui!, ids, additive),
    setHidden: (ids, hide) => setHidden(app, ids, hide),
    hover: (id) => {
      app.hoverId = id;
    },
  });
  modelPane.append(filterRow, tree.root);

  const sets = new SetsView(
    {
      selection: () => app.selection,
      select: (ids, additive) => selectFromUi(ui!, ids, additive),
      frame: (ids) => frameIds(app, ids),
    },
    store,
  );
  const setsPane = el('div', 'sb-pane');
  setsPane.append(sets.root);
  body.append(modelPane, setsPane);

  const props = new PropsView();
  sidebar.append(top, railLabel, body, props.root);

  const u: Ui = {
    app,
    sidebar,
    toggle,
    tabs,
    panes: { model: modelPane, sets: setsPane },
    filter,
    filterInfo,
    tree,
    sets,
    props,
    store,
    state: readState(store),
    lastSelection: [],
    fromUi: false,
    lastRefresh: 0,
  };

  toggle.addEventListener('click', () => setCollapsed(u, !u.state.collapsed));
  railLabel.addEventListener('click', () => setCollapsed(u, false));
  tabs.model.addEventListener('click', () => setTab(u, 'model'));
  tabs.sets.addEventListener('click', () => setTab(u, 'sets'));
  const applyFilter = debounce(() => {
    tree.setFilter(filter.value);
    updateFilterInfo(u);
  }, 150);
  filter.addEventListener('input', applyFilter);
  filter.addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'Escape' && filter.value) {
      filter.value = '';
      tree.setFilter('');
      updateFilterInfo(u);
    } else if (e.key === 'Escape') {
      filter.blur();
    }
  });
  // `[` toggles the sidebar through the action registry (keymap plugin owns the key).
  registerAction({
    id: 'panel.left',
    label: 'Toggle model tree',
    group: 'Panels',
    keys: ['['],
    run: () => setCollapsed(u, !u.state.collapsed),
  });

  // The canvas fills #stage; whenever the stage changes size (toggle, window, mobile overlay) resize the renderer.
  if (typeof ResizeObserver !== 'undefined') new ResizeObserver(() => resizeRenderer(app)).observe(app.canvas);
  sidebar.addEventListener('transitionend', (e) => {
    if (e.propertyName === 'width') resizeRenderer(app);
  });

  applyState(u);
  return u;
}

export const sidebarPlugin: AppPlugin = {
  name: 'sidebar',

  install(app) {
    const sidebar = document.getElementById('sidebar');
    if (!sidebar) {
      console.warn('sidebar plugin: #sidebar not found in the page; sidebar disabled');
      return;
    }
    ui = buildDom(app, sidebar);
    resizeRenderer(app);
  },

  onModel(app) {
    const u = ui;
    if (!u || !app.loaded) return;
    u.filter.value = '';
    u.filterInfo.textContent = '';
    u.tree.setModel(app.loaded.model);
    u.sets.setModel(app.loaded.model, app.modelName);
    u.lastSelection = [];
    refreshAll(u);
  },

  onStatic(app) {
    const u = ui;
    if (!u) return;
    const sel = app.selection;
    const changed = !sameIds(sel, u.lastSelection);
    u.lastSelection = sel;
    if (changed && !u.fromUi && sel.length > 0) u.tree.reveal(sel[0]!);
    u.lastRefresh = performance.now();
    refreshAll(u);
  },

  afterFrame(app, now) {
    const u = ui;
    if (!u || now - u.lastRefresh < REFRESH_MS) return;
    u.lastRefresh = now;
    refreshAll(u);
  },
};
