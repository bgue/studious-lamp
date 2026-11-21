// Label placement: greedy, one tag per element near its anchor, no tag over another, over the caption or the hover card, or off
// the frame. Pure, tested in tests/hud-place.test.ts.

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface LabelIn {
  key: number;
  /** Where the element is on screen (CSS pixels). */
  x: number;
  y: number;
  /** Size of the tag. */
  w: number;
  h: number;
}

export interface LabelOut {
  key: number;
  /** Top left of the tag. */
  x: number;
  y: number;
  w: number;
  h: number;
  /** The anchor (end of the leader line). */
  ax: number;
  ay: number;
}

export interface PlaceOptions {
  /** At most this many tags (default 12). */
  max?: number;
  /** Distance of a tag from the frame edge. */
  margin?: number;
  /** Distance of a tag from its anchor. */
  gap?: number;
  /** Clear space around a tag. */
  pad?: number;
}

export const MAX_LABELS = 12;

export function overlaps(a: Rect, b: Rect, pad = 0): boolean {
  return a.x < b.x + b.w + pad && b.x < a.x + a.w + pad && a.y < b.y + b.h + pad && b.y < a.y + a.h + pad;
}

/**
 * Place the tags in the order given (the caller sorts: the most important first). Each tries up-right, up-left, down-right,
 * down-left, right and left of its anchor and takes the first spot that is inside the frame and clear of `occupied` and of the tags
 * placed before it. A tag that finds no spot, and every tag beyond `max`, is counted in `more`.
 */
export function placeLabels(items: readonly LabelIn[], view: { w: number; h: number }, occupied: readonly Rect[] = [], opts: PlaceOptions = {}): { placed: LabelOut[]; more: number } {
  const max = opts.max ?? MAX_LABELS;
  const m = opts.margin ?? 6;
  const gap = opts.gap ?? 14;
  const pad = opts.pad ?? 3;
  const taken: Rect[] = [...occupied];
  const placed: LabelOut[] = [];
  let more = 0;
  for (const it of items) {
    if (placed.length >= max) {
      more++;
      continue;
    }
    const spots: Array<[number, number]> = [
      [it.x + gap, it.y - gap - it.h],
      [it.x - gap - it.w, it.y - gap - it.h],
      [it.x + gap, it.y + gap],
      [it.x - gap - it.w, it.y + gap],
      [it.x + gap, it.y - it.h / 2],
      [it.x - gap - it.w, it.y - it.h / 2],
    ];
    let hit: Rect | null = null;
    for (const [sx, sy] of spots) {
      const r: Rect = { x: Math.min(Math.max(sx, m), Math.max(m, view.w - m - it.w)), y: Math.min(Math.max(sy, m), Math.max(m, view.h - m - it.h)), w: it.w, h: it.h };
      if (r.x < 0 || r.y < 0 || r.x + r.w > view.w || r.y + r.h > view.h) continue;
      // A tag clamped over its own anchor would hide the element: keep the anchor clear.
      if (it.x >= r.x - 2 && it.x <= r.x + r.w + 2 && it.y >= r.y - 2 && it.y <= r.y + r.h + 2) continue;
      if (taken.some((o) => overlaps(r, o, pad))) continue;
      hit = r;
      break;
    }
    if (!hit) {
      more++;
      continue;
    }
    taken.push(hit);
    placed.push({ key: it.key, x: hit.x, y: hit.y, w: hit.w, h: hit.h, ax: it.x, ay: it.y });
  }
  return { placed, more };
}

/** The point of `r` nearest to (px, py): where a leader line ends on a tag. */
export function nearestOnRect(r: Rect, px: number, py: number): { x: number; y: number } {
  return { x: Math.min(Math.max(px, r.x), r.x + r.w), y: Math.min(Math.max(py, r.y), r.y + r.h) };
}
