// Search bar plugin: builds the bar (src/ui/awesomeBar.ts), mounts it in the top bar's search host, indexes each model
// in idle time and registers the focus action. Docs: docs-features/search.md.
//
// Mount: the top bar plugin creates an empty element #xray-topbar-search; the bar moves into it as soon as it exists
// (MutationObserver). Until then, and on a page without a top bar, the bar sits in a small fixed box at the top centre of
// #stage (the fallback in place()).
//
// Keys: `/` and Ctrl+K (Meta+K) focus the bar (action search.focus). The old owners of those chords keep a key:
// the command palette moves to Ctrl+Shift+K and the sidebar filter to Alt+F. When the bar is not available (kiosk, XR),
// search.focus runs the old action for the chord instead.

import type { AppPlugin, ViewerApp } from '../app';
import { getAction, registerAction } from '../input/actions';
import type { XrayAction } from '../input/actions';
import { ElementIndex } from '../search/elementIndex';
import { SearchSources } from '../search/sources';
import { bootConfig } from '../tools/registry';
import { AwesomeBar } from '../ui/awesomeBar';
import { showToast } from '../ui/keymapView';

export const SEARCH_HOST_ID = 'xray-topbar-search';
/** Models up to this many elements are indexed at once; larger ones in idle slices. */
export const SYNC_INDEX_LIMIT = 20000;

declare global {
  interface Window {
    /** For scripts and the smoke test: the bar and its state. */
    __xraySearch?: {
      bar: AwesomeBar;
      sources: SearchSources;
      state: AwesomeBar['state'];
      indexReady(): boolean;
    };
  }
}

let bar: AwesomeBar | null = null;
let sources: SearchSources | null = null;
let observer: MutationObserver | null = null;
let oldPalette: XrayAction | undefined;
let oldFilter: XrayAction | undefined;

/** Put the bar in the top bar host when it exists, else in the fallback box on #stage. Safe to call again. */
function place(): void {
  const b = bar;
  if (!b) return;
  const host = document.getElementById(SEARCH_HOST_ID);
  if (host) {
    if (b.root.parentElement !== host) {
      b.root.classList.remove('ab-fallback');
      host.appendChild(b.root);
    }
    return;
  }
  const stage = document.getElementById('stage') ?? document.body;
  if (b.root.parentElement !== stage) {
    b.root.classList.add('ab-fallback');
    stage.appendChild(b.root);
  }
}

function barAvailable(): boolean {
  return !!bar && !bar.hidden && bar.root.isConnected;
}

function indexModel(app: ViewerApp): void {
  const s = sources;
  if (!s || !app.loaded) return;
  s.index?.cancel();
  const idx = new ElementIndex(app.loaded.model);
  s.index = idx;
  s.invalidate();
  if (idx.size <= SYNC_INDEX_LIMIT) {
    idx.buildAll();
    bar?.refresh();
  } else {
    void idx.buildIdle({ onProgress: () => bar?.refresh() }).then(() => bar?.refresh());
  }
}

export const awesomeBarPlugin: AppPlugin = {
  name: 'awesomeBar',

  install(app) {
    sources = new SearchSources(app, showToast);
    bar = new AwesomeBar(app, sources);
    window.__xraySearch = { bar, sources, state: () => bar!.state(), indexReady: () => !!sources?.index?.ready };

    // The chords: take `/` and Ctrl+K, give the old owners other keys.
    oldPalette = getAction('palette.open');
    oldFilter = getAction('sidebar.filter');
    if (oldPalette) registerAction({ ...oldPalette, keys: ['Ctrl+Shift+k', 'Meta+Shift+k'] });
    if (oldFilter) registerAction({ ...oldFilter, keys: ['Alt+f'] });
    registerAction({
      id: 'search.focus',
      label: 'Search',
      group: 'Navigation',
      keys: ['/', 'Ctrl+k', 'Meta+k'],
      description: 'Focus the search bar: elements, commands, presets, views, sets and settings.',
      run(a, ev) {
        if (barAvailable()) {
          bar!.focus();
          return;
        }
        // No bar (kiosk, XR session): the key does what it did before.
        const fallback = ev?.key === '/' ? getAction('sidebar.filter') : getAction('palette.open');
        fallback?.run(a, ev);
      },
    });

    place();
    observer = new MutationObserver(() => place());
    observer.observe(document.body, { childList: true, subtree: true });

    if (bootConfig().kiosk) bar.setHidden(true);
  },

  onModel(app) {
    indexModel(app);
  },

  afterFrame(app) {
    if (!bar || bootConfig().kiosk) return;
    bar.setHidden(app.renderer.xrPresenting);
  },
};
