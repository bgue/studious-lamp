// Which keys a focused list widget keeps from the global keymap. Pure (no DOM at import): the keymap plugin passes the
// widget's mode and the key event. Docs: docs-features/keyboard.md (Focus rules).
//
// A widget is any element with role tree, listbox or grid, or with a `data-keys-own` attribute. Its mode:
//   all  arrows, Home/End, PageUp/PageDown, Enter, Space and every plain character (type-ahead, letters) stay in the widget
//   nav  the same without the letters: the widget decides itself which letters it takes (the model tree does type-ahead
//        only for letters without a global action) and calls stopPropagation for them
// Ctrl, Alt and Meta chords always reach the global actions. Shift only counts with Up/Down (extend the selection) and,
// in `all` mode, with characters.

export type OwnMode = 'all' | 'nav';

export interface OwnKeyLike {
  key: string;
  ctrlKey?: boolean;
  altKey?: boolean;
  metaKey?: boolean;
  shiftKey?: boolean;
}

const NAV_KEYS = new Set(['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown', 'Enter', ' ']);

export const OWN_SELECTOR = '[role="tree"], [role="listbox"], [role="grid"], [data-keys-own]';

/** Mode of a widget from its attributes: `data-keys-own="nav"` or `"all"`; a bare attribute or a role means `all`, except role tree (`nav`). */
export function ownMode(role: string | null, attr: string | null): OwnMode {
  if (attr === 'nav') return 'nav';
  if (attr !== null) return 'all';
  return role === 'tree' ? 'nav' : 'all';
}

/** True when the widget in `mode` keeps this key from the global keymap. */
export function widgetOwnsKey(mode: OwnMode, ev: OwnKeyLike): boolean {
  if (ev.ctrlKey || ev.altKey || ev.metaKey) return false;
  if (ev.shiftKey) {
    if (ev.key === 'ArrowUp' || ev.key === 'ArrowDown') return true;
    return mode === 'all' && ev.key.length === 1;
  }
  if (NAV_KEYS.has(ev.key)) return true;
  return mode === 'all' && ev.key.length === 1;
}

export interface ElLike {
  closest?(sel: string): ElLike | null;
  getAttribute?(name: string): string | null;
}

/** The closest list widget around a key target and its mode, or null. */
export function focusOwnerOf(target: unknown): { el: ElLike; mode: OwnMode } | null {
  const t = target as ElLike | null;
  if (!t || typeof t.closest !== 'function') return null;
  const el = t.closest(OWN_SELECTOR);
  if (!el) return null;
  return { el, mode: ownMode(el.getAttribute?.('role') ?? null, el.getAttribute?.('data-keys-own') ?? null) };
}
