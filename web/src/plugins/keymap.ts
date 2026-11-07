// Keyboard plugin: owns the window key listeners, the keymap (rebinding, conflicts, persistence), the navigation and
// selection actions, the cheat sheet (?), the command palette (Ctrl+Shift+K), the shortcut editor and the `Keyboard` folder.
// Docs: docs-features/keyboard.md.

import type { AppPlugin, ViewerApp } from '../app';
import { registerAction } from '../input/actions';
import { Keymap, setKeymap } from '../input/keymap';
import {
  bindMouseHistory,
  isNavigationMoving,
  cancelNavigationMoves,
  loadNavSettings,
  navSettings,
  navigationFrame,
  navigationOnModel,
  registerNavigationActions,
  saveNavSettings,
} from '../input/navigation';
import { registerCommandActions } from '../input/commands';
import { registerParamSection } from '../ui/params';
import { MemoryStorage } from '../selectionSets';
import type { StorageLike } from '../selectionSets';
import { CheatSheet } from '../ui/cheatsheet';
import { PaletteView } from '../ui/palette';
import { KeymapEditor, ensureKeyStyles, showToast } from '../ui/keymapView';

function storage(): StorageLike {
  try {
    const s = window.localStorage;
    s.getItem('xray.probe');
    return s;
  } catch {
    return new MemoryStorage();
  }
}

declare global {
  interface Window {
    __keymap?: Keymap;
    /** For scripts: true while a keyboard-started camera tween runs. */
    __keymapMoving?: () => boolean;
  }
}

export const keymapPlugin: AppPlugin = {
  name: 'keymap',

  install(app: ViewerApp) {
    ensureKeyStyles();
    const store = storage();
    const km = new Keymap({ storage: store });
    setKeymap(km);
    window.__keymap = km;
    window.__keymapMoving = isNavigationMoving;
    loadNavSettings(store);
    registerNavigationActions();
    registerCommandActions();

    const editor = new KeymapEditor(km);
    const cheat = new CheatSheet(km, () => editor.open());
    const palette = new PaletteView(app, km);
    registerAction({ id: 'help.cheatsheet', label: 'Keyboard shortcuts', group: 'Other', keys: ['?', 'F1'], run: () => cheat.toggle() });
    registerAction({ id: 'palette.open', label: 'Command palette', group: 'Other', keys: ['Ctrl+k', 'Meta+k'], run: () => palette.toggle() });
    registerAction({ id: 'keys.edit', label: 'Edit shortcuts', group: 'Other', keys: [], run: () => editor.open() });
    registerAction({ id: 'keys.reset', label: 'Reset shortcuts', group: 'Other', keys: [], run: () => { km.resetAll(); showToast('Shortcuts reset to the defaults'); } });

    km.load();
    km.watchRegistry();

    // Key listeners. Bubble phase on window, so a field that stops propagation (the sidebar filter) keeps its keys.
    window.addEventListener('keydown', (e) => {
      if (!app.controller) return;
      if (e.key === 'Tab') {
        // Keep Tab for keyboard focus movement unless the focus is on the page itself.
        const t = e.target as HTMLElement | null;
        if (t && t !== document.body && t !== app.canvas && t !== document.documentElement) return;
      }
      try {
        km.handleKeyDown(e, app);
      } catch (err) {
        console.error('[keymap] action failed', err);
      }
    });
    window.addEventListener('keyup', (e) => km.handleKeyUp(e));
    window.addEventListener('blur', () => km.clearPressed());
    document.addEventListener('visibilitychange', () => km.clearPressed());
    app.canvas.addEventListener('pointerdown', cancelNavigationMoves);
    app.canvas.addEventListener('wheel', cancelNavigationMoves, { passive: true });
    bindMouseHistory(app);

    registerParamSection('keymap', {
      collect: () => (Object.keys(km.overrides).length ? { ...km.overrides } : undefined),
      apply(value, bad, path) {
        try {
          const r = km.importJson(JSON.stringify({ bindings: value }));
          for (const b of r.bad) bad.push(`${path}.${b}`);
        } catch {
          bad.push(path);
        }
      },
    });

    if (app.panel) buildGui(app, km, store, cheat, palette, editor);
  },

  onModel(app) {
    navigationOnModel(app);
  },

  onFrame(app, now, dt) {
    if (app.controller) {
      window.__keymap?.tick(app, dt);
      navigationFrame(app, now);
    }
  },
};

function buildGui(app: ViewerApp, km: Keymap, store: StorageLike, cheat: CheatSheet, palette: PaletteView, editor: KeymapEditor): void {
  const f = app.panel!.addFolder('Keyboard');
  const save = (): void => saveNavSettings(store);
  f.add(navSettings, 'enabled').name('keyboard navigation').onChange(save);
  f.add(navSettings, 'orbitSpeed', 10, 360, 5).name('orbit speed (deg/s)').onChange(save);
  f.add(navSettings, 'panSpeed', 0.1, 4, 0.1).name('pan speed').onChange(save);
  f.add(navSettings, 'moveSpeed', 0.1, 4, 0.1).name('move speed').onChange(save);
  f.add(navSettings, 'invertVertical').name('invert vertical').onChange(save);
  f.add(navSettings, 'smoothMoves').name('smooth moves').onChange(save);
  const buttons = {
    sheet: () => cheat.toggle(),
    edit: () => editor.open(),
    palette: () => palette.toggle(),
    reset: () => {
      km.resetAll();
      showToast('Shortcuts reset to the defaults');
    },
  };
  f.add(buttons, 'sheet').name('Shortcuts (?)');
  f.add(buttons, 'edit').name('Edit shortcuts');
  f.add(buttons, 'palette').name('Command palette (Ctrl+Shift+K)');
  f.add(buttons, 'reset').name('Reset shortcuts');
  f.close();
}
