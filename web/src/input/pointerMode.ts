// Pointer mode: what a left-button drag does in the viewport. A per-viewer convenience, like the sidebar width: it is kept in
// localStorage only. It is never written into the params document, a share link, a saved view, a preset or a packed page
// (tests/pointer-mode.test.ts checks that no params section carries it).
//
//   hand   (move, the default)  left drag orbits, right or Shift drag pans, wheel and pinch zoom; a click selects.
//   arrow  (select)             left drag draws a selection box; right and middle drag and the wheel still move the camera;
//                               on touch one finger draws the box and two fingers orbit and zoom.
// No DOM access at import time; the storage is injected, so the module runs in vitest.

export type PointerMode = 'hand' | 'arrow';

export const POINTER_MODE_KEY = 'xray.pointerMode';
export const DEFAULT_POINTER_MODE: PointerMode = 'hand';

export interface StorageLike {
  getItem(k: string): string | null;
  setItem(k: string, v: string): void;
}

export function parsePointerMode(v: unknown): PointerMode | null {
  return v === 'hand' || v === 'arrow' ? v : null;
}

export function loadPointerMode(storage: StorageLike | null): PointerMode {
  try {
    return parsePointerMode(storage?.getItem(POINTER_MODE_KEY)) ?? DEFAULT_POINTER_MODE;
  } catch {
    return DEFAULT_POINTER_MODE;
  }
}

export function savePointerMode(storage: StorageLike | null, mode: PointerMode): void {
  try {
    storage?.setItem(POINTER_MODE_KEY, mode);
  } catch {
    /* private mode: the mode lasts for the session */
  }
}

/** three's MOUSE and TOUCH numbers, for the controls that this module configures without importing three. */
export const MOUSE_ROTATE = 0;
export const MOUSE_DOLLY = 1;
export const MOUSE_PAN = 2;
export const TOUCH_ROTATE = 0;
export const TOUCH_PAN = 1;
export const TOUCH_DOLLY_PAN = 2;
export const TOUCH_DOLLY_ROTATE = 3;
/** "No action" for a button or a touch count. */
export const NONE = -1;

export interface ControlsLike {
  mouseButtons: { LEFT?: number | null; MIDDLE?: number | null; RIGHT?: number | null };
  touches: { ONE?: number | null; TWO?: number | null };
}

/**
 * Set the orbit controls for a mode. Hand: the defaults of OrbitControls (left rotates, Shift or right pans, one finger
 * rotates, two fingers zoom and pan). Arrow: the left button and one finger do nothing to the camera (the box takes them);
 * the middle button zooms, the right button pans, two fingers zoom and orbit.
 */
export function configureControls(c: ControlsLike, mode: PointerMode): void {
  c.mouseButtons.MIDDLE = MOUSE_DOLLY;
  c.mouseButtons.RIGHT = MOUSE_PAN;
  if (mode === 'hand') {
    c.mouseButtons.LEFT = MOUSE_ROTATE;
    c.touches.ONE = TOUCH_ROTATE;
    c.touches.TWO = TOUCH_DOLLY_PAN;
  } else {
    c.mouseButtons.LEFT = NONE;
    c.touches.ONE = NONE;
    c.touches.TWO = TOUCH_DOLLY_ROTATE;
  }
}

/** How a click or a box combines with the selection: Shift adds, Ctrl or Cmd toggles, nothing replaces. */
export type SelectHow = 'replace' | 'add' | 'toggle';

export function selectHowOf(e: { shiftKey?: boolean; ctrlKey?: boolean; metaKey?: boolean }): SelectHow {
  if (e.ctrlKey || e.metaKey) return 'toggle';
  if (e.shiftKey) return 'add';
  return 'replace';
}

/** The new selection for ids picked with `how`. A box with Ctrl or Cmd toggles each picked element. */
export function combineSelection(current: Iterable<number>, picked: readonly number[], how: SelectHow): number[] {
  if (how === 'replace') return [...picked];
  const set = new Set(current);
  if (how === 'add') {
    for (const id of picked) set.add(id);
  } else {
    for (const id of picked) {
      if (set.has(id)) set.delete(id);
      else set.add(id);
    }
  }
  return [...set];
}
