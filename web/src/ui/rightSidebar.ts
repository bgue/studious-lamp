// The right-hand sidebar: a tabbed column that mirrors the left sidebar (collapse chevron, 28 px rail, state in localStorage).
// Pure DOM, no app dependency: the plugin (plugins/rightSidebar.ts) fills it with the Properties, Classification and
// Parameters tabs, and any other feature adds its own with `addTab`.
//
//   const tab = rightSidebar.addTab({ id: 'revision', label: 'Revision', mount: (pane, ctx) => { ...build into pane...; return () => cleanup } });
//   tab.show();      // open the sidebar (when collapsed) and switch to the tab
//
// How to add a tab (the integration point for other features):
//   * `window.__xrayRightSidebar.addTab(spec)` (or `addRightSidebarTab(spec)` from src/plugins/rightSidebar.ts when you import);
//     it works before and after the page has built the sidebar: a tab added early is kept and appears when the column exists.
//   * `mount(pane, ctx)` runs once, the first time the tab is shown (not at registration), with an empty flex-column <div>.
//     `ctx.visible()` says whether the tab is on screen now; `ctx.onVisible(cb)` runs `cb(true|false)` when it is shown or hidden;
//     `ctx.setBadge(text)` puts a short count or mark on the tab button. Return a function to run when the tab is removed.
//   * `order` sorts the tabs (the built-in ones are 10, 20, 30; the default is 100: after them, in the order added).
//   * `width` is the preferred width in px while the tab is shown (default 300; the Classification tab asks for 420).
//   * ids are unique: addTab with a known id returns the existing handle.
//   * on a phone (max-width 700 px) the same column is a bottom sheet with the same tabs; the left sidebar and this one never
//     both stay open there (opening one closes the other), so a tab never needs to know.
//   * the column is #dock, an edge chrome of the overlay: `ov.reserve` rects and the gizmo, drawing toolbar and top bar keep
//     clear of it through the overlay's insets, and on a phone sheet it is registered as `ov.reserved` too.
// Persistence: `xray.dock` = { collapsed: boolean, tab: string }; `dk-collapsed` is mirrored on <body> (index.html applies it
// before first paint, like `sb-collapsed` for the left sidebar). Key `]` toggles it (action `panel.right`).

import { el } from './dom';
import { registerAction } from '../input/actions';

export const DOCK_KEY = 'xray.dock';
export const DOCK_TRANSITION_MS = 220;
export const DEFAULT_TAB = 'properties';
export const DEFAULT_WIDTH = 300;
export const PHONE_QUERY = '(max-width: 700px)';

export interface DockState {
  collapsed: boolean;
  tab: string;
}

export interface DockStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

/** Parse the stored state; `narrow` (viewport <= 700 px) is the default for "collapsed" when nothing valid is stored. */
export function parseDockState(raw: string | null, narrow: boolean): DockState {
  let collapsed = narrow;
  let tab = DEFAULT_TAB;
  try {
    const v = JSON.parse(raw ?? 'null') as Partial<DockState> | null;
    if (v && typeof v.collapsed === 'boolean') collapsed = v.collapsed;
    if (v && typeof v.tab === 'string' && v.tab) tab = v.tab;
  } catch {
    /* corrupt: fall through to the defaults */
  }
  return { collapsed, tab };
}

export interface RightTabContext {
  /** The tab is on screen now (the sidebar is open on it). */
  visible(): boolean;
  /** Runs when the tab is shown or hidden (also when the sidebar collapses or expands). Returns an unsubscribe function. */
  onVisible(cb: (visible: boolean) => void): () => void;
  /** A short mark on the tab button (a count); empty text removes it. */
  setBadge(text: string): void;
  /** Open the sidebar on this tab. */
  show(): void;
}

export interface RightTabSpec {
  id: string;
  label: string;
  /** Builds the content into `pane`, once, on the first show. May return a cleanup function. */
  mount(pane: HTMLElement, ctx: RightTabContext): (() => void) | void;
  /** Sort key; built-in tabs use 10, 20, 30. Default 100. */
  order?: number;
  /** Preferred sidebar width in px while this tab is shown (default 300). */
  width?: number;
  /** Tooltip of the tab button. */
  title?: string;
  /** Help popover key of the tab button (data-help-key). */
  helpKey?: string;
}

export interface RightTabHandle {
  readonly id: string;
  /** Open the sidebar (when collapsed) and switch to this tab. */
  show(): void;
  /** The sidebar is open on this tab. */
  visible(): boolean;
  /** Take the tab away (its cleanup runs); the sidebar falls back to the first tab. */
  remove(): void;
  setBadge(text: string): void;
}

export interface DockOptions {
  /** Called after the layout changed (immediately, and once more when the width transition has ended). */
  onResize?: () => void;
  storage?: DockStorage | null;
  narrow?: boolean;
}

interface TabRec {
  spec: RightTabSpec;
  button: HTMLButtonElement;
  badge: HTMLElement;
  pane: HTMLElement;
  mounted: boolean;
  cleanup: (() => void) | null;
  listeners: Set<(v: boolean) => void>;
  shown: boolean;
  handle: RightTabHandle;
}

export class RightSidebar {
  readonly host: HTMLElement;
  readonly toggle: HTMLButtonElement;
  readonly tabsEl: HTMLElement;
  readonly body: HTMLElement;
  readonly railLabel: HTMLElement;
  state: DockState;

  private readonly store: DockStorage | null;
  private readonly onResize: () => void;
  private readonly recs = new Map<string, TabRec>();
  private readonly changeListeners = new Set<() => void>();

  constructor(host: HTMLElement, opts: DockOptions = {}) {
    this.host = host;
    this.store = opts.storage ?? null;
    this.onResize = opts.onResize ?? (() => undefined);
    let raw: string | null = null;
    try {
      raw = this.store?.getItem(DOCK_KEY) ?? null;
    } catch {
      raw = null;
    }
    this.state = parseDockState(raw, opts.narrow ?? false);

    host.textContent = '';
    const top = el('div', 'dk-top');
    this.toggle = el('button', 'dk-toggle', { type: 'button', 'aria-controls': 'dk-body' });
    this.tabsEl = el('div', 'dk-tabs', { role: 'tablist', 'aria-label': 'Right sidebar' });
    top.append(this.toggle, this.tabsEl);
    this.railLabel = el('div', 'dk-rail-label', {}, 'Properties');
    this.body = el('div', 'dk-body', { id: 'dk-body' });
    host.append(top, this.railLabel, this.body);

    this.toggle.addEventListener('click', () => this.setCollapsed(!this.state.collapsed));
    this.railLabel.addEventListener('click', () => this.setCollapsed(false));
    host.addEventListener('transitionend', (e) => {
      if (e.propertyName === 'width') this.onResize();
    });
    // `]` toggles the sidebar through the action registry (keymap plugin owns the key).
    registerAction({
      id: 'panel.right',
      label: 'Toggle right sidebar',
      group: 'Panels',
      keys: [']'],
      run: () => this.setCollapsed(!this.state.collapsed),
    });
    this.apply();
  }

  /** Called after any change of the collapsed flag or the active tab. */
  onChange(cb: () => void): () => void {
    this.changeListeners.add(cb);
    return () => this.changeListeners.delete(cb);
  }

  tabIds(): string[] {
    return [...this.recs.keys()];
  }

  /** The tab that is shown (a stored tab that no feature registered shows the first one). */
  get activeTab(): string {
    return this.recs.has(this.state.tab) ? this.state.tab : this.firstTab();
  }

  private firstTab(): string {
    return this.recs.keys().next().value ?? DEFAULT_TAB;
  }

  paneOf(id: string): HTMLElement | null {
    return this.recs.get(id)?.pane ?? null;
  }

  /** Add a tab. Returns the existing handle for a known id. */
  addTab(spec: RightTabSpec): RightTabHandle {
    const known = this.recs.get(spec.id);
    if (known) return known.handle;
    const attrs: Record<string, string> = { type: 'button', role: 'tab', 'data-tab': spec.id, 'aria-controls': `dk-pane-${spec.id}` };
    if (spec.title) attrs['title'] = spec.title;
    if (spec.helpKey) {
      attrs['data-help-key'] = spec.helpKey;
      attrs['data-help-title'] = `${spec.label} tab`;
    }
    const button = el('button', 'dk-tab', attrs, spec.label);
    const badge = el('span', 'dk-badge');
    badge.hidden = true;
    button.append(badge);
    const pane = el('div', 'dk-pane', { id: `dk-pane-${spec.id}`, role: 'tabpanel', 'data-pane': spec.id });
    pane.style.display = 'none';
    const rec: TabRec = {
      spec, button, badge, pane, mounted: false, cleanup: null, listeners: new Set(), shown: false,
      handle: {
        id: spec.id,
        show: () => this.showTab(spec.id),
        visible: () => !this.state.collapsed && this.activeTab === spec.id,
        remove: () => this.removeTab(spec.id),
        setBadge: (t) => {
          badge.textContent = t;
          badge.hidden = t === '';
        },
      },
    };
    button.addEventListener('click', () => this.showTab(spec.id));
    this.recs.set(spec.id, rec);
    // Keep the tabs sorted by order, then by the order added.
    const sorted = [...this.recs.values()].sort((a, b) => (a.spec.order ?? 100) - (b.spec.order ?? 100));
    this.recs.clear();
    for (const r of sorted) this.recs.set(r.spec.id, r);
    this.tabsEl.replaceChildren(...sorted.map((r) => r.button));
    this.body.append(pane);
    this.apply();
    return rec.handle;
  }

  removeTab(id: string): void {
    const rec = this.recs.get(id);
    if (!rec) return;
    this.recs.delete(id);
    try {
      rec.cleanup?.();
    } catch (e) {
      console.warn('[rightSidebar] tab cleanup failed', e);
    }
    rec.button.remove();
    rec.pane.remove();
    this.apply();
  }

  /** Open the sidebar when collapsed and switch to a tab. False for an unknown id. */
  showTab(id: string): boolean {
    if (!this.recs.has(id)) return false;
    this.state.tab = id;
    this.state.collapsed = false;
    this.commit(true);
    return true;
  }

  /** `persist` false: the change is not stored (an automatic collapse on a phone must not overwrite the wide-screen choice). */
  setCollapsed(collapsed: boolean, persist = true): void {
    this.state.collapsed = collapsed;
    this.commit(true, persist);
  }

  /** The tab is on screen now (open sidebar, this tab active). */
  tabsVisible(id: string): boolean {
    return !this.state.collapsed && this.activeTab === id;
  }

  private commit(layout: boolean, persist = true): void {
    this.apply();
    if (persist) {
      try {
        this.store?.setItem(DOCK_KEY, JSON.stringify(this.state));
      } catch {
        /* ignore */
      }
    }
    if (layout) {
      // The canvas resizes with the stage (ResizeObserver); this also covers the end of the width transition.
      this.onResize();
      window.setTimeout(this.onResize, DOCK_TRANSITION_MS);
    }
    for (const cb of this.changeListeners) cb();
  }

  private apply(): void {
    const c = this.state.collapsed;
    const active = this.activeTab;
    document.body.classList.toggle('dk-collapsed', c);
    this.toggle.setAttribute('aria-expanded', String(!c));
    this.toggle.title = c ? 'Expand right sidebar (])' : 'Collapse right sidebar (])';
    this.toggle.textContent = c ? '‹' : '›';
    const rec = this.recs.get(active);
    this.railLabel.textContent = rec?.spec.label ?? 'Properties';
    this.host.style.setProperty('--dk-w', `${rec?.spec.width ?? DEFAULT_WIDTH}px`);
    for (const r of this.recs.values()) {
      const on = r.spec.id === active;
      r.button.classList.toggle('active', on);
      r.button.setAttribute('aria-selected', String(on));
      r.pane.style.display = on ? '' : 'none';
      const visible = on && !c;
      if (visible && !r.mounted) {
        r.mounted = true;
        try {
          const cleanup = r.spec.mount(r.pane, {
            visible: () => r.shown,
            onVisible: (cb) => {
              r.listeners.add(cb);
              return () => r.listeners.delete(cb);
            },
            setBadge: (t) => r.handle.setBadge(t),
            show: () => this.showTab(r.spec.id),
          });
          r.cleanup = typeof cleanup === 'function' ? cleanup : null;
        } catch (e) {
          r.pane.append(el('div', 'dk-error', {}, `Could not build ${r.spec.label}: ${e instanceof Error ? e.message : String(e)}`));
          console.warn('[rightSidebar] tab mount failed', e);
        }
      }
      if (visible !== r.shown) {
        r.shown = visible;
        for (const cb of [...r.listeners]) {
          try {
            cb(visible);
          } catch (e) {
            console.warn('[rightSidebar] tab listener failed', e);
          }
        }
      }
    }
  }
}

let current: RightSidebar | null = null;
const queued: RightTabSpec[] = [];

/** The sidebar of this page, or null before it is built. */
export function getRightSidebar(): RightSidebar | null {
  return current;
}

export function setRightSidebar(s: RightSidebar | null): void {
  current = s;
  if (s) {
    for (const spec of queued.splice(0)) {
      s.addTab(spec);
    }
  }
}

/**
 * Add a tab to the right sidebar (the integration point for other features; see the top of this file). Safe to call before the
 * sidebar exists: the spec is kept and the tab appears when the column is built. The returned handle works at once (it acts
 * when the column exists).
 */
export function addRightSidebarTab(spec: RightTabSpec): RightTabHandle {
  if (current) return current.addTab(spec);
  if (!queued.some((q) => q.id === spec.id)) queued.push(spec);
  const lazy = (): RightTabHandle | null => (current?.tabIds().includes(spec.id) ? current.addTab(spec) : null);
  return {
    id: spec.id,
    show: () => void lazy()?.show(),
    visible: () => lazy()?.visible() ?? false,
    remove: () => {
      const i = queued.findIndex((q) => q.id === spec.id);
      if (i >= 0) queued.splice(i, 1);
      lazy()?.remove();
    },
    setBadge: (t) => lazy()?.setBadge(t),
  };
}
