// Time budget of one slice of main-thread work that yields to the event loop between slices.
//
// A slice must stay short so a click, key or pointer move is handled within about one slice plus one drawn frame. When
// the gap since the last slice was long (a heavy frame was drawn in between) the slice grows a little so the work still
// makes progress, but never beyond `maxMs`: the old cap of 250 ms let one click wait seconds behind a run of long slices.

/** Longest a slice may run, milliseconds. */
export const MAX_SLICE_MS = 30;

/** The slice length for the next slice: `baseMs`, grown by half the last gap, clamped to [baseMs, maxMs]. */
export function nextSliceMs(baseMs: number, gapMs: number, maxMs: number = MAX_SLICE_MS): number {
  const base = Math.min(baseMs, maxMs);
  const g = Number.isFinite(gapMs) && gapMs > 0 ? gapMs : 0;
  return Math.min(maxMs, Math.max(base, g * 0.5));
}

/** Yield to the event loop as a macrotask, so queued input events are dispatched before the work continues. */
export function yieldMacrotask(): Promise<void> {
  return new Promise((r) => setTimeout(r, 0));
}
