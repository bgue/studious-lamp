// What a sketch on a placed sheet is attached to in the model. Pure: the shape in plan metres and the cut outlines of the elements
// (sectionCut.ts) come in, an Attachment of src/bcf/attach.ts goes out, so the sketch is stored the way a 3D sketch is and exports
// with GlobalIds. Tested in tests/sheets-placement-attach.test.ts. Docs: docs-features/sheets.md ("Attachment").
//
// The same words as the 3D flow, but the shape is looked at from above: the elements that the plan cut shows (the ones the plane
// at storey + 1.2 m slices) are what is "under" a shape on a plan sheet.
//
//   a point (text, callout, pointer, a tiny shape) on an element     point (with the element's GlobalId)
//   an outline over or around one to a dozen elements                  elements (the outline lies on the plan as `surface` data)
//   a line over up to five elements                                    surface
//   nothing under it, or more than a dozen elements                    region: the shape's bounds at the level, the storey height band

import type { Attachment, SurfaceData, SurfacePoint } from '../bcf/attach';
import type { Vec3 } from '../bcf/model';
import { distCut, polygonTouchesCut } from './sectionCut';
import type { CutElement } from './sectionCut';

export const SHEET_ATTACH = {
  /** More elements than this under an outline: a region instead. */
  maxElements: 12,
  /** A line over at most this many elements is `surface`. */
  surfaceElements: 5,
  /** A point is on an element when it is inside its outline, or this close to it (m). */
  pointTol: 0.1,
  /** A line touches an element within this distance of its outline (m). */
  lineTol: 0.12,
  /** Bounds of a closed shape below this (m) make it a point. */
  tinyShape: 0.3,
  /** Region padding around the shape (m) and around a bare point. */
  pad: 0.05,
  pointPad: 0.5,
  /** The outline lies this far above the level (m): on the sheet's plane, clear of the floor. */
  lift: 0.05,
  /** Default storey height when the next level is unknown (m). */
  storeyHeight: 3,
} as const;

export interface DeriveInput {
  /** The shape's path in plan metres, flat (rect: 4 corners, ellipse: its points, cloud: its base). */
  path: number[];
  /** Box-like outline (cloud, rect, ellipse, polygon, highlight box). */
  closed: boolean;
  /** A text, callout or pointer: one point (`path` holds it). */
  anchored?: boolean;
  /** What the plan cut shows. */
  cut: readonly CutElement[];
  /** Level elevation and the top of the storey band (metres, IFC frame). */
  level: { elevation: number; top?: number };
}

export interface DeriveResult {
  attach: Attachment;
  /** Why, in a few words (tests, status line). */
  reason: string;
  /** The elements found under the shape, whatever the attachment kind. */
  found: string[];
}

function bounds(path: readonly number[]): { x0: number; y0: number; x1: number; y1: number } {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (let i = 0; i + 1 < path.length; i += 2) { x0 = Math.min(x0, path[i]!); x1 = Math.max(x1, path[i]!); y0 = Math.min(y0, path[i + 1]!); y1 = Math.max(y1, path[i + 1]!); }
  return { x0, y0, x1, y1 };
}

const r3 = (x: number): number => Math.round(x * 1e3) / 1e3;

export function regionAround(path: readonly number[], level: { elevation: number; top?: number }, pad: number): Attachment {
  const b = bounds(path);
  const top = level.top !== undefined && level.top > level.elevation + 0.5 ? level.top : level.elevation + SHEET_ATTACH.storeyHeight;
  return {
    kind: 'region',
    region: { min: [r3(b.x0 - pad), r3(b.y0 - pad), r3(level.elevation)], max: [r3(b.x1 + pad), r3(b.y1 + pad), r3(top)] },
  };
}

/** The outline as `surface` data on the plan: each point on the element nearest to it (index into `guids`). */
function surfaceOn(path: readonly number[], closed: boolean, guids: readonly string[], els: readonly CutElement[], z: number): SurfaceData {
  const pts: SurfacePoint[] = [];
  for (let i = 0; i + 1 < path.length; i += 2) {
    const x = path[i]!, y = path[i + 1]!;
    let e = 0;
    let best = Infinity;
    els.forEach((el, k) => { const d = distCut(el, x, y); if (d < best) { best = d; e = k; } });
    pts.push({ e, p: [r3(x), r3(y), r3(z)], n: [0, 0, 1] });
  }
  return { guids: [...guids], pts, closed };
}

/** Decide the attachment of a shape on a plan sheet from the cut outlines. */
export function deriveSheetAttachment(inp: DeriveInput): DeriveResult {
  const A = SHEET_ATTACH;
  const path = inp.path;
  const n = path.length / 2;
  if (n < 1) return { attach: { kind: 'none' }, reason: 'no points', found: [] };
  const b = bounds(path);
  const size = Math.max(b.x1 - b.x0, b.y1 - b.y0);
  const z = inp.level.elevation + A.lift;
  const point = inp.anchored || n === 1 || size < 1e-6 || (inp.closed && size < A.tinyShape);
  // Elements under the shape.
  const els: Array<{ e: CutElement; d: number }> = [];
  if (point) {
    const x = (b.x0 + b.x1) / 2, y = (b.y0 + b.y1) / 2;
    for (const e of inp.cut) {
      const d = distCut(e, x, y);
      if (d <= A.pointTol) els.push({ e, d });
    }
  } else if (inp.closed) {
    for (const e of inp.cut) if (polygonTouchesCut(path, e)) els.push({ e, d: 0 });
  } else {
    for (const e of inp.cut) {
      let d = Infinity;
      // Samples along the path: every vertex and the middle of each stretch longer than the tolerance.
      for (let i = 0; i < n && d > A.lineTol; i++) {
        const x0 = path[i * 2]!, y0 = path[i * 2 + 1]!;
        d = Math.min(d, distCut(e, x0, y0));
        if (i + 1 < n) {
          const x1 = path[i * 2 + 2]!, y1 = path[i * 2 + 3]!;
          const k = Math.max(1, Math.min(60, Math.ceil(Math.hypot(x1 - x0, y1 - y0) / A.lineTol)));
          for (let s = 1; s < k && d > A.lineTol; s++) d = Math.min(d, distCut(e, x0 + ((x1 - x0) * s) / k, y0 + ((y1 - y0) * s) / k));
        }
      }
      if (d <= A.lineTol) els.push({ e, d });
    }
  }
  els.sort((p, q) => p.d - q.d || (p.e.guid < q.e.guid ? -1 : 1));
  const found = els.map((x) => x.e.guid);
  if (point) {
    if (!found.length) return { attach: regionAround(path, inp.level, A.pointPad), reason: 'nothing under the point', found };
    return { attach: { kind: 'point', guids: [found[0]!] }, reason: 'a point on an element', found };
  }
  if (!found.length) return { attach: regionAround(path, inp.level, A.pad), reason: 'nothing under the shape', found };
  if (found.length > A.maxElements) return { attach: regionAround(path, inp.level, A.pad), reason: `${found.length} elements under the shape`, found };
  const list = els.map((x) => x.e);
  const surface = surfaceOn(path, inp.closed, found, list, z);
  if (!inp.closed && found.length <= A.surfaceElements) return { attach: { kind: 'surface', surface }, reason: `a line over ${found.length} element(s)`, found };
  return { attach: { kind: 'elements', guids: found, surface }, reason: `${found.length} element(s) under the outline`, found };
}

/** The 3D position of a `point` attachment's anchor: the point on the sheet at the level (IFC frame). */
export function anchorAt(xy: readonly [number, number], level: { elevation: number }): Vec3 {
  return [xy[0], xy[1], level.elevation + SHEET_ATTACH.lift];
}
