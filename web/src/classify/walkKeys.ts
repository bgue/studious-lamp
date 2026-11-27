// The keys of the review walk, as pure functions: which action a key means, what Esc does, and how a code list is filtered when you type.
// No DOM: the walk (plugins/classifyReview.ts) reads the focus and passes it in, tests drive these directly.

export type WalkAction =
  | 'confirm' | 'candidate' | 'correct' | 'skip' | 'skip-other' | 'unsure' | 'back' | 'step-next' | 'step-prev' | 'scope' | 'undo' | 'frame' | 'zoom' | 'close';

export interface KeyInput {
  /** `KeyboardEvent.key`. */
  key: string;
  shift?: boolean;
}

/** The action of a key in the walk when no correction is open and no text field has the keyboard. `candidate` carries the rank (1 to 9). */
export function walkKeyAction(k: KeyInput): { action: WalkAction; rank?: number } | null {
  const key = k.key.length === 1 ? k.key.toLowerCase() : k.key;
  if (/^[1-9]$/.test(key)) return key === '1' ? { action: 'confirm' } : { action: 'candidate', rank: Number(key) };
  switch (key) {
    case 'Enter': case 'y': return { action: 'confirm' };
    case 'e': return { action: 'correct' };
    case 'n': return { action: k.shift ? 'skip-other' : 'skip' };
    case 'ArrowRight': return { action: 'skip' };
    case '?': return { action: 'unsure' };
    case 'ArrowLeft': return { action: 'back' };
    case ']': return { action: 'step-next' };
    case '[': return { action: 'step-prev' };
    case 'a': return { action: 'scope' };
    case 'u': return { action: 'undo' };
    case 'f': return { action: 'frame' };
    case 'z': return { action: 'zoom' };
    case 'q': return { action: 'close' };
    default: return null;
  }
}

/** The second Esc closes the walk when it comes within this time of the first. */
export const ESC_CLOSE_MS = 1500;

export type EscFocus = 'walk' | 'field' | 'elsewhere';

/**
 * What Esc does. `editing`: a correction is open. `focus`: `walk` when the focus is on the walk panel (or the page), `field` when it is in a
 * text field or list of the panel, `elsewhere` when it is on a control outside the panel. `armedAt`: the time of a first Esc, or null.
 *   leave-edit   close the correction, keep the walk
 *   focus-walk   put the focus back on the walk (a field, or a control elsewhere); the walk stays open
 *   arm          first Esc: show "Esc again to close"
 *   close        second Esc within ESC_CLOSE_MS
 */
export function escAction(o: { editing: boolean; focus: EscFocus; armedAt: number | null; now: number }): 'leave-edit' | 'focus-walk' | 'arm' | 'close' {
  if (o.editing) return 'leave-edit';
  if (o.focus !== 'walk') return 'focus-walk';
  return o.armedAt !== null && o.now - o.armedAt <= ESC_CLOSE_MS ? 'close' : 'arm';
}

/** Keep the options of a code list that match what was typed: every word must be in the code or the label. An empty filter keeps all. */
export function filterCodes<T extends { code: string; label: string }>(list: readonly T[], text: string, keep?: string): T[] {
  const words = text.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return [...list];
  return list.filter((x) => x.code === keep || words.every((w) => x.code.toLowerCase().includes(w) || x.label.toLowerCase().includes(w)));
}
