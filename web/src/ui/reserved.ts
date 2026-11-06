// Reserved screen rects: parts of the view that viewer chrome covers (the gizmo, the status bar, an open tool drawer,
// legends). Labels and markers drawn on the shared overlay (measure labels, penetration markers, BCF pins and callouts)
// move out of them to the nearest free spot, with a leader line back to their anchor. Pure: no DOM; tested in node.

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** CSS pixels of the canvas covered by viewer chrome along each edge (status bar, tool strip and drawer, phone rails). */
export interface Insets {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export function rectsOverlap(a: Rect, b: Rect, gap = 0): boolean {
  return a.x < b.x + b.w + gap && a.x + a.w + gap > b.x && a.y < b.y + b.h + gap && a.y + a.h + gap > b.y;
}

export function pointInRect(x: number, y: number, r: Rect): boolean {
  return x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h;
}

/** True when the point lies under one of the rects. */
export function underReserved(x: number, y: number, reserved: readonly Rect[]): boolean {
  return reserved.some((r) => pointInRect(x, y, r));
}

/** The edge chrome as rects of a `width` x `height` view (one strip per non-zero inset). */
export function insetRects(width: number, height: number, ins: Insets): Rect[] {
  const out: Rect[] = [];
  if (ins.top > 0) out.push({ x: 0, y: 0, w: width, h: ins.top });
  if (ins.bottom > 0) out.push({ x: 0, y: height - ins.bottom, w: width, h: ins.bottom });
  if (ins.left > 0) out.push({ x: 0, y: 0, w: ins.left, h: height });
  if (ins.right > 0) out.push({ x: width - ins.right, y: 0, w: ins.right, h: height });
  return out;
}

export interface Spot {
  /** Centre of the box. */
  x: number;
  y: number;
  /** False when the box could stay where it was asked for. */
  moved: boolean;
}

export interface SpotOptions {
  /** Clearance kept to the reserved rects, px (default 4). */
  gap?: number;
  /** Largest move, px (default: unlimited). Farther spots give null (callers show an edge marker instead). */
  maxShift?: number;
}

/**
 * Where a box of `w` x `h` centred on (x, y) can go: unchanged when it overlaps no reserved rect and lies inside
 * `area`; otherwise the nearest centre (straight-line distance) at which the box clears every rect by `gap` and stays
 * inside `area`. The candidates sit just outside the rect sides (and the area sides), so a box under the gizmo moves
 * left of it or above it, whichever is nearer. Null when no candidate is free within `maxShift`.
 */
export function freeSpot(x: number, y: number, w: number, h: number, reserved: readonly Rect[], area: Rect, opts: SpotOptions = {}): Spot | null {
  const gap = opts.gap ?? 4;
  const maxShift = opts.maxShift ?? Infinity;
  const hw = w / 2;
  const hh = h / 2;
  const inArea = (cx: number, cy: number): boolean =>
    cx - hw >= area.x - 0.5 && cx + hw <= area.x + area.w + 0.5 && cy - hh >= area.y - 0.5 && cy + hh <= area.y + area.h + 0.5;
  const clear = (cx: number, cy: number): boolean => {
    const b = { x: cx - hw, y: cy - hh, w, h };
    for (const r of reserved) if (r.w > 0 && r.h > 0 && rectsOverlap(b, r, gap - 0.01)) return false;
    return true;
  };
  if (inArea(x, y) && clear(x, y)) return { x, y, moved: false };
  const clampX = (v: number): number => Math.min(area.x + area.w - hw, Math.max(area.x + hw, v));
  const clampY = (v: number): number => Math.min(area.y + area.h - hh, Math.max(area.y + hh, v));
  const xs = new Set<number>([clampX(x)]);
  const ys = new Set<number>([clampY(y)]);
  for (const r of reserved) {
    if (r.w <= 0 || r.h <= 0) continue;
    xs.add(r.x - gap - hw);
    xs.add(r.x + r.w + gap + hw);
    ys.add(r.y - gap - hh);
    ys.add(r.y + r.h + gap + hh);
  }
  let best: Spot | null = null;
  let bestD = Infinity;
  for (const cx of xs) for (const cy of ys) {
    const d = Math.hypot(cx - x, cy - y);
    if (d >= bestD || d > maxShift || !inArea(cx, cy) || !clear(cx, cy)) continue;
    bestD = d;
    best = { x: cx, y: cy, moved: true };
  }
  return best;
}
