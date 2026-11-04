// Action registry: the single list of user commands that keyboard shortcuts, the command
// palette, the cheat sheet and presets can trigger. Plugins register actions in install().
// The keymap plugin (plugins/keymap.ts) owns dispatch, user rebinding and the cheat sheet;
// this module only holds the list, so any plugin can register without importing the keymap.

import type { ViewerApp } from '../app';

export interface XrayAction {
  /** Stable id, dotted: 'view.top', 'select.clear', 'peel.toggle'. Used as the rebinding key. */
  id: string;
  /** Short label shown in the cheat sheet and the command palette. */
  label: string;
  /** Group heading in the cheat sheet: 'Navigation', 'Views', 'Selection', 'Visibility', 'Modes', 'Panels', 'Presets', ... */
  group: string;
  /**
   * Default key chords. Syntax: optional modifiers 'Ctrl+', 'Alt+', 'Shift+', 'Meta+' then a key name
   * as KeyboardEvent.key (case-insensitive for letters: 'x', 'F', '[', '?', 'Escape', 'ArrowLeft', 'Home')
   * or a KeyboardEvent.code prefixed with 'code:' for layout-independent keys ('code:Numpad7', 'code:Digit1').
   */
  keys: string[];
  /** Run the action. `repeat` is true for auto-repeat key events. */
  run(app: ViewerApp, ev?: KeyboardEvent): void;
  /** Optional: return false to skip (the key then falls through to other handlers). */
  enabled?(app: ViewerApp): boolean;
  /**
   * Optional: continuous action held down (navigation). Called every frame while held, with dt in ms and the
   * modifier keys currently down (a hold action may scale its speed by them, see `modifiers`).
   */
  hold?(app: ViewerApp, dt: number, mods?: HoldMods): void;
  /** Optional: let auto-repeat key events run a discrete action again (zoom steps). Default false. */
  repeat?: boolean;
  /**
   * Optional: modifier keys that may be down in addition to the chord, without changing which action runs
   * (a hold action reads them from `hold(..., mods)`). An exact chord of another action always wins.
   */
  modifiers?: Array<'ctrl' | 'shift' | 'alt' | 'meta'>;
  /** Optional: one line of help for the cheat sheet and the palette. */
  description?: string;
}

export interface HoldMods {
  ctrl: boolean;
  shift: boolean;
  alt: boolean;
  meta: boolean;
}

const ACTIONS = new Map<string, XrayAction>();
const listeners = new Set<() => void>();

/** Register or replace an action by id. Returns an unregister function. */
export function registerAction(a: XrayAction): () => void {
  ACTIONS.set(a.id, a);
  for (const l of listeners) l();
  return () => {
    if (ACTIONS.get(a.id) === a) {
      ACTIONS.delete(a.id);
      for (const l of listeners) l();
    }
  };
}

export function getAction(id: string): XrayAction | undefined {
  return ACTIONS.get(id);
}

export function getActions(): XrayAction[] {
  return [...ACTIONS.values()];
}

/** Subscribe to registry changes. Returns an unsubscribe function. */
export function onActionsChanged(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

/** Run an action by id if it exists and is enabled. Returns true when it ran. */
export function runAction(app: ViewerApp, id: string): boolean {
  const a = ACTIONS.get(id);
  if (!a || (a.enabled && !a.enabled(app))) return false;
  a.run(app);
  return true;
}
