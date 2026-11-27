// How far the review walk frames the element in view: Close, With surroundings, Room or Storey. Pure (numbers only): the walk gives the
// boxes and gets back the box to frame with its margin and closest distance, so tests pin every mode.
//
//   close         the element(s) alone: margin 1.6 for one element, 1.15 for a group (the framing the walk always had)
//   surroundings  the default: margin 2.5, never nearer than 4 m, so a small fitting shows what it hangs on
//   room          the IfcSpace that holds the element's centre (same storey when both know it); no room known: a wide margin
//   storey        the storey of the element (the box of its elements); no storey known: the same wide margin

import type { WalkElement } from './reviewWalk';

export const REVIEW_ZOOMS = ['close', 'surroundings', 'room', 'storey'] as const;
export type ReviewZoom = (typeof REVIEW_ZOOMS)[number];
export const DEFAULT_REVIEW_ZOOM: ReviewZoom = 'surroundings';
export const REVIEW_ZOOM_LABEL: Record<ReviewZoom, string> = { close: 'Close', surroundings: 'With surroundings', room: 'Room', storey: 'Storey' };
export const isReviewZoom = (v: unknown): v is ReviewZoom => (REVIEW_ZOOMS as readonly unknown[]).includes(v);

/** The next zoom in the cycle (the Z key). */
export const nextReviewZoom = (z: ReviewZoom): ReviewZoom => REVIEW_ZOOMS[(REVIEW_ZOOMS.indexOf(z) + 1) % REVIEW_ZOOMS.length]!;

export type Box6 = readonly [number, number, number, number, number, number];

export const SURROUNDINGS = { margin: 2.5, minDistance: 4 } as const;
/** The margin and closest distance when a room or a storey is asked for and none is known. */
export const WIDE = { margin: 4, minDistance: 8 } as const;

export interface ZoomContext {
  /** The room (IfcSpace) of the element, or null. */
  room?: Box6 | null;
  /** The box of the element's storey, or null. */
  storey?: Box6 | null;
}

export interface ZoomView {
  /** The box to frame. */
  box: Box6;
  margin: number;
  /** Never nearer than this (m); 0 for none. */
  minDistance: number;
  /** What was actually used (a room zoom without a room falls back to `wide`). */
  used: ReviewZoom | 'wide';
}

export function unionBox(boxes: readonly Box6[]): Box6 | null {
  if (boxes.length === 0) return null;
  const o: [number, number, number, number, number, number] = [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity];
  for (const b of boxes) {
    for (let i = 0; i < 3; i++) { o[i] = Math.min(o[i]!, b[i]!); o[i + 3] = Math.max(o[i + 3]!, b[i + 3]!); }
  }
  return o;
}

/** The view for a zoom mode. `targets` are the elements in view (one, or a type group). */
export function resolveZoom(mode: ReviewZoom, targets: readonly Box6[], ctx: ZoomContext = {}): ZoomView | null {
  const own = unionBox(targets);
  if (!own) return null;
  switch (mode) {
    case 'close':
      return { box: own, margin: targets.length > 1 ? 1.15 : 1.6, minDistance: 0, used: 'close' };
    case 'surroundings':
      return { box: own, ...SURROUNDINGS, used: 'surroundings' };
    case 'room':
      return ctx.room ? { box: ctx.room, margin: 1.1, minDistance: 0, used: 'room' } : { box: own, ...WIDE, used: 'wide' };
    case 'storey':
      return ctx.storey ? { box: ctx.storey, margin: 1.05, minDistance: 0, used: 'storey' } : { box: own, ...WIDE, used: 'wide' };
  }
}

export interface SpaceBox {
  bounds: Box6;
  storey: number | null;
}

const volume = (b: Box6): number => Math.max(0, b[3] - b[0]) * Math.max(0, b[4] - b[1]) * Math.max(0, b[5] - b[2]);

/**
 * The room of an element: the smallest IfcSpace whose box holds the centre of the element's box (on the same storey when both have one).
 * Null when no space does. `spaces` are the IfcSpace elements of the model.
 */
export function roomOf(bounds: Box6, storey: number | null, spaces: readonly SpaceBox[]): Box6 | null {
  const c = [(bounds[0] + bounds[3]) / 2, (bounds[1] + bounds[4]) / 2, (bounds[2] + bounds[5]) / 2];
  let best: SpaceBox | null = null;
  for (const s of spaces) {
    if (storey !== null && s.storey !== null && s.storey !== storey) continue;
    const b = s.bounds;
    if (c[0]! < b[0] || c[0]! > b[3] || c[1]! < b[1] || c[1]! > b[4] || c[2]! < b[2] || c[2]! > b[5]) continue;
    if (!best || volume(b) < volume(best.bounds)) best = s;
  }
  return best?.bounds ?? null;
}

/** The box of a storey: every walk element on it. Null for an element without a storey. */
export function storeyBox(storey: number | null, elements: readonly Pick<WalkElement, 'storey' | 'bounds'>[]): Box6 | null {
  if (storey === null) return null;
  return unionBox(elements.filter((e) => e.storey === storey).map((e) => e.bounds));
}
