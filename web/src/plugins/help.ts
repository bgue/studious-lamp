// Help plugin: hover tooltips (Intent, Impact, Use, Ref) for every setting and for the sidebar.
//
// It does not touch the plugins that build the controls. After every other plugin has installed it walks the
// lil-gui tree, derives a key for each control and folder (see src/ui/help.ts) and registers the row element.
// It walks again on every onModel (the class style folders are rebuilt for each model) and once more 1 s later for
// late folders. Sidebar and dock items are found by selectors. Any element with a data-help-key attribute works too.
//
//   window.__xrayHelp = { enable(), disable(), lookup(key), keys() }
//   localStorage['xray.help'] === 'off' turns the tooltips off.

import type GUI from 'lil-gui';
import type { AppPlugin, ViewerApp } from '../app';
import {
  HelpPopover,
  ELEMENT_RULES,
  classOf,
  controllerAltKey,
  controllerKey,
  domTarget,
  DOM_CANDIDATES,
  drawerTitleOf,
  folderKey,
  folderTitle,
  helpEnabled,
  lookupHelp,
  type ControllerLike,
  type GuiLike,
  type HelpTarget,
} from '../ui/help';
import { HELP, type HelpEntry } from '../ui/helpText';

declare global {
  interface Window {
    __xrayHelp?: { enable(): void; disable(): void; lookup(key: string): HelpEntry | undefined; keys(): string[]; popover?: HelpPopover };
  }
}

type Anchored = HelpTarget & { anchor: HTMLElement };

const STORAGE_KEY = 'xray.help';
const LATE_MS = 1000;

/** Row element -> target, for lil-gui controls and folder titles. */
const registry = new WeakMap<HTMLElement, HelpTarget>();
const warned = new Set<string>();
let popover: HelpPopover | null = null;
let lateTimer: ReturnType<typeof setTimeout> | null = null;

function bind(el: HTMLElement, key: string, alt: string | null, title: string, cls: string | null, kind: string): void {
  if (registry.has(el)) return; // keep the first key: some controls rename themselves (Play tour, Stop tour)
  let k = key;
  if (!lookupHelp(k) && alt && lookupHelp(alt)) k = alt;
  registry.set(el, { key: k, title, cls });
  el.setAttribute('data-help-key', k);
  if (!lookupHelp(k)) {
    const id = `${kind}:${k}`;
    if (!warned.has(id)) {
      warned.add(id);
      console.warn(`[help] no help text for ${kind} "${k}"`);
    }
  }
}

/** Register every control and folder of the panel. Safe to call again; known elements are skipped. */
export function attach(panel: GUI): { controls: number; folders: number } {
  let controls = 0;
  let folders = 0;
  const gui = panel as unknown as GuiLike & { $title: HTMLElement; foldersRecursive(): GUI[]; controllersRecursive(): unknown[] };
  for (const f of [gui, ...(panel.foldersRecursive() as unknown as Array<GuiLike & { $title: HTMLElement }>)]) {
    bind(f.$title, folderKey(f), null, folderTitle(f), classOf(f), 'folder');
    folders++;
  }
  for (const c of panel.controllersRecursive() as unknown as Array<ControllerLike & { domElement: HTMLElement }>) {
    const name = (c._name ?? c.property ?? '').trim();
    bind(c.domElement, controllerKey(c), controllerAltKey(c), name, classOf(c.parent), 'control');
    controls++;
  }
  return { controls, folders };
}

function labelOf(key: string): string {
  const i = key.lastIndexOf('/');
  return i >= 0 ? key.slice(i + 1) : key;
}

/** Map a hovered node to the element that carries help, walking up to the body. */
export function resolveTarget(node: Node | null): Anchored | null {
  let n: Element | null = node instanceof Element ? node : (node?.parentElement ?? null);
  for (; n && n !== document.body && n !== document.documentElement; n = n.parentElement) {
    const el = n as HTMLElement;
    const reg = registry.get(el);
    if (reg) return { ...reg, anchor: el };
    const dk = el.getAttribute('data-help-key');
    if (dk) return { key: dk, title: el.getAttribute('data-help-title') ?? labelOf(dk), anchor: el };
    for (const r of ELEMENT_RULES) {
      if (!el.matches(r.selector)) continue;
      const key = typeof r.key === 'function' ? r.key(el) : r.key;
      if (!key) continue;
      return { key, title: typeof r.title === 'function' ? r.title(el) : r.title, anchor: el };
    }
    const dom = domTarget(el);
    if (dom) return { ...dom, anchor: el };
  }
  return null;
}

function setStored(v: 'on' | 'off'): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, v);
  } catch {
    /* privacy mode: the in-memory flag still works */
  }
}

function attachAll(app: ViewerApp): void {
  if (app.panel) attach(app.panel);
  scanTools();
}

/** Warn once for each element of the strip, a drawer or a dialog that has no help text. Same message as attach(). */
export function scanTools(root: ParentNode = document): number {
  let missing = 0;
  for (const node of Array.from(root.querySelectorAll(DOM_CANDIDATES))) {
    const t = domTarget(node);
    if (!t) continue;
    node.setAttribute('data-help-key', t.key);
    node.setAttribute('data-help-title', t.title);
    if (lookupHelp(t.key)) continue;
    missing++;
    const kind = node.closest('#xray-toolbar-drawer') ? `drawer "${drawerTitleOf(node)}"` : node.closest('#xray-toolbar') ? 'tool strip' : 'dialog';
    const id = `${kind}:${t.key}`;
    if (!warned.has(id)) {
      warned.add(id);
      console.warn(`[help] no help text for ${kind} "${t.key}"`);
    }
  }
  return missing;
}

let toolObserver: MutationObserver | null = null;
let scanTimer: ReturnType<typeof setTimeout> | null = null;

/** Scan the strip, drawers and dialogs now and whenever they change. */
function watchTools(): void {
  scanTools();
  if (toolObserver || typeof MutationObserver === 'undefined') return;
  toolObserver = new MutationObserver(() => {
    if (scanTimer) return;
    scanTimer = setTimeout(() => {
      scanTimer = null;
      scanTools();
    }, 60);
  });
  toolObserver.observe(document.body, { childList: true, subtree: true });
}

function setBodyClass(on: boolean): void {
  document.body.classList.toggle('xh-on', on);
}

export const helpPlugin: AppPlugin = {
  name: 'help',

  install(app) {
    popover = new HelpPopover({ resolve: resolveTarget });
    window.__xrayHelp = {
      enable() {
        setStored('on');
        popover?.setEnabled(true);
        setBodyClass(true);
      },
      disable() {
        setStored('off');
        popover?.setEnabled(false);
        setBodyClass(false);
      },
      lookup: (key) => lookupHelp(key),
      keys: () => Object.keys(HELP),
      popover,
    };
    setBodyClass(helpEnabled());
    attachAll(app);
    watchTools();
  },

  onModel(app) {
    attachAll(app);
    if (lateTimer) clearTimeout(lateTimer);
    lateTimer = setTimeout(() => {
      lateTimer = null;
      attachAll(app);
    }, LATE_MS);
  },
};
