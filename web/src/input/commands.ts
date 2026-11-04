// Selection, visibility and utility actions. Camera actions are in navigation.ts; panel toggles are registered by
// the sidebar and the dock themselves; the cheat sheet, palette and editor actions by plugins/keymap.ts.

import type { ViewerApp } from '../app';
import type { ElementId } from '../types';
import { getAction, registerAction } from './actions';
import { showToast } from '../ui/keymapView';

/** Elements the user has not hidden: what "select all" means. */
export function visibleIds(app: ViewerApp): ElementId[] {
  const hides = app.controller.settings.overrides.userHides;
  const out: ElementId[] = [];
  const n = app.controller.model.elements.length;
  for (let i = 0; i < n; i++) if (!hides.has(i)) out.push(i);
  return out;
}

/** Ids of the visible elements that are not in `selection`. */
export function invertIds(visible: readonly ElementId[], selection: ReadonlySet<ElementId>): ElementId[] {
  return visible.filter((id) => !selection.has(id));
}

/** Visible elements whose IFC class is one of the classes of the selection. */
export function sameClassIds(
  elements: ReadonlyArray<{ ifcClass: string }>,
  selection: ReadonlySet<ElementId>,
  hidden: ReadonlySet<ElementId>,
): ElementId[] {
  const classes = new Set<string>();
  for (const id of selection) {
    const c = elements[id]?.ifcClass;
    if (c) classes.add(c);
  }
  const out: ElementId[] = [];
  for (let i = 0; i < elements.length; i++) if (classes.has(elements[i]!.ifcClass) && !hidden.has(i)) out.push(i);
  return out;
}

const hasSelection = (app: ViewerApp): boolean => !!app.controller && app.controller.selection.size > 0;

function refreshHides(app: ViewerApp): void {
  app.controller.refreshOverrides();
  app.runSightlinesNow();
}

export function registerCommandActions(): void {
  registerAction({
    id: 'select.all',
    label: 'Select all visible',
    group: 'Selection',
    keys: ['Ctrl+a'],
    run(app) {
      const ids = visibleIds(app);
      app.selectIds(ids);
      showToast(`Selected ${ids.length}`);
    },
  });
  registerAction({
    id: 'select.invert',
    label: 'Invert selection',
    group: 'Selection',
    keys: ['Ctrl+i'],
    run(app) {
      const ids = invertIds(visibleIds(app), app.controller.selection);
      app.selectIds(ids);
      showToast(`Selected ${ids.length}`);
    },
  });
  registerAction({
    id: 'select.sameClass',
    label: 'Select all of the same class',
    group: 'Selection',
    keys: ['Alt+s'],
    enabled: hasSelection,
    run(app) {
      const ids = sameClassIds(app.controller.model.elements, app.controller.selection, app.controller.settings.overrides.userHides);
      app.selectIds(ids);
      showToast(`Selected ${ids.length} of the same class`);
    },
  });

  registerAction({
    id: 'visibility.hide',
    label: 'Hide selected',
    group: 'Visibility',
    keys: ['h'],
    enabled: hasSelection,
    run(app) {
      const n = app.controller.selection.size;
      app.hideSelected();
      showToast(`Hid ${n}`);
    },
  });
  registerAction({
    id: 'visibility.unhideAll',
    label: 'Unhide all',
    group: 'Visibility',
    keys: ['Alt+h'],
    description: 'Clears the elements you hid. Pins stay.',
    run(app) {
      const hides = app.controller.settings.overrides.userHides;
      const n = hides.size;
      hides.clear();
      refreshHides(app);
      showToast(n ? `Unhid ${n}` : 'Nothing was hidden');
    },
  });
  registerAction({
    id: 'visibility.isolate',
    label: 'Hide everything not selected',
    group: 'Visibility',
    keys: ['Shift+h'],
    enabled: hasSelection,
    run(app) {
      const c = app.controller;
      const hides = c.settings.overrides.userHides;
      const n = c.model.elements.length;
      for (let i = 0; i < n; i++) {
        if (c.selection.has(i)) hides.delete(i);
        else hides.add(i);
      }
      refreshHides(app);
      showToast(`Isolated ${c.selection.size}`);
    },
  });

  registerAction({
    id: 'sidebar.filter',
    label: 'Find in the model tree',
    group: 'Other',
    keys: ['/'],
    description: 'Open the sidebar and focus its filter box.',
    run(app) {
      if (document.body.classList.contains('sb-collapsed')) getAction('panel.left')?.run(app);
      const input = document.querySelector<HTMLInputElement>('.sb-filter input');
      if (!input) return;
      input.focus();
      input.select();
    },
  });

  // Placeholders: the presets plugin replaces them by id. Never overwrite a real registration.
  for (let n = 1; n <= 9; n++) {
    const id = `preset.${n}`;
    if (getAction(id)) continue;
    registerAction({ id, label: `Preset ${n}`, group: 'Presets', keys: [`code:Digit${n}`], run() { /* until the presets plugin replaces it */ } });
  }
}
