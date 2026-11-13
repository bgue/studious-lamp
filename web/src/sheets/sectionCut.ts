// A horizontal cut through the model as vectors: the outline every element makes where a plane at one height slices it. Pure: no
// DOM, no three.js. Tested in tests/sheets-placement-cut.test.ts. Docs: docs-features/sheets.md ("Model overlay").
//
// The overlay draws these outlines over the sheet, the placement view draws them next to the sheet and snaps to their corners
// and edges, and the attachment of a sketch asks them what lies under a shape. One slice of the triangles of the elements that
// straddle the plane, chained into polylines, with straight runs merged, costs a few milliseconds for a building and is sharp at
// every zoom, so nothing is rendered to a picture and nothing has to be redrawn when the zoom settles.

export interface Poly {
  /** x0, y0, x1, y1, ... plan metres. */
  pts: number[];
  closed: boolean;
}

export interface CutElement {
  guid: string;
  cls?: string;
  polys: Poly[];
  /** Plan bounds of the outlines: x0, y0, x1, y1. */
  box: [number, number, number, number];
}

export interface PlanCut {
  /** The height of the cut, metres (IFC frame). */
  z: number;
  elements: CutElement[];
}

const KEY = 1e-4;

/**
 * The segments where the plane `v = level` cuts the triangles. `pos`: xyz per vertex, `v` is the vertical axis index (1 for the
 * viewer frame, 2 for the IFC frame); the other two axes are returned as (a, b) pairs: for v = 1 that is (x, z), for v = 2 (x, y).
 * Triangles that only touch the plane along an edge or a vertex give nothing, one lying in the plane gives nothing.
 */
export function sliceMesh(pos: ArrayLike<number>, index: ArrayLike<number> | null, level: number, v = 1): number[] {
  const a = v === 0 ? 1 : 0;
  const b = v === 2 ? 1 : 2;
  const out: number[] = [];
  const n = index ? index.length : Math.floor(pos.length / 9) * 3;
  const at = (i: number): number => (index ? index[i]! : i);
  const dv = [0, 0, 0];
  const pa = [0, 0, 0];
  const pb = [0, 0, 0];
  for (let t = 0; t + 2 < n; t += 3) {
    for (let k = 0; k < 3; k++) {
      const i = at(t + k) * 3;
      dv[k] = pos[i + v]! - level;
      pa[k] = pos[i + a]!;
      pb[k] = pos[i + b]!;
    }
    const lo = Math.min(dv[0]!, dv[1]!, dv[2]!);
    const hi = Math.max(dv[0]!, dv[1]!, dv[2]!);
    if (!(lo < 0 && hi > 0)) continue; // not crossing the plane through its inside
    const pts: number[] = [];
    for (let k = 0; k < 3; k++) {
      const m = (k + 1) % 3;
      const d0 = dv[k]!;
      const d1 = dv[m]!;
      if ((d0 < 0 && d1 > 0) || (d0 > 0 && d1 < 0)) {
        const f = d0 / (d0 - d1);
        pts.push(pa[k]! + (pa[m]! - pa[k]!) * f, pb[k]! + (pb[m]! - pb[k]!) * f);
      } else if (d0 === 0) pts.push(pa[k]!, pb[k]!);
    }
    if (pts.length >= 4 && (pts[0] !== pts[2] || pts[1] !== pts[3])) out.push(pts[0]!, pts[1]!, pts[2]!, pts[3]!);
  }
  return out;
}

const qk = (x: number, y: number): string => `${Math.round(x / KEY)},${Math.round(y / KEY)}`;

/** Chain loose segments into polylines (shared endpoints join), and drop vertices on a straight run. */
export function chainSegments(segs: ArrayLike<number>, straightDeg = 1): Poly[] {
  const n = Math.floor(segs.length / 4);
  const adj = new Map<string, number[]>();
  const link = (k: string, i: number): void => { const l = adj.get(k); if (l) l.push(i); else adj.set(k, [i]); };
  for (let i = 0; i < n; i++) { link(qk(segs[i * 4]!, segs[i * 4 + 1]!), i); link(qk(segs[i * 4 + 2]!, segs[i * 4 + 3]!), i); }
  const used = new Uint8Array(n);
  const polys: Poly[] = [];
  /** Walk from point (x, y) along unused segments, returning the points passed. */
  const walk = (x: number, y: number): Array<[number, number]> => {
    const out: Array<[number, number]> = [];
    for (;;) {
      const cand = (adj.get(qk(x, y)) ?? []).find((i) => !used[i]);
      if (cand === undefined) return out;
      used[cand] = 1;
      const sx = segs[cand * 4]!, sy = segs[cand * 4 + 1]!, ex = segs[cand * 4 + 2]!, ey = segs[cand * 4 + 3]!;
      const forward = qk(sx, sy) === qk(x, y);
      x = forward ? ex : sx;
      y = forward ? ey : sy;
      out.push([x, y]);
    }
  };
  for (let s = 0; s < n; s++) {
    if (used[s]) continue;
    used[s] = 1;
    const x0 = segs[s * 4]!, y0 = segs[s * 4 + 1]!, x1 = segs[s * 4 + 2]!, y1 = segs[s * 4 + 3]!;
    const tail = walk(x1, y1);
    const head = walk(x0, y0);
    const pts: Array<[number, number]> = [...head.reverse(), [x0, y0], [x1, y1], ...tail];
    let closed = false;
    const first = pts[0]!, last = pts[pts.length - 1]!;
    if (pts.length > 3 && Math.abs(first[0] - last[0]) < KEY * 2 && Math.abs(first[1] - last[1]) < KEY * 2) { closed = true; pts.pop(); }
    polys.push({ pts: straighten(pts.flatMap((q) => q), closed, straightDeg), closed });
  }
  return polys;
}

/** Remove vertices whose neighbours are in a straight line (turn of less than `deg`), and doubled points. */
export function straighten(pts: number[], closed: boolean, deg = 1): number[] {
  const cos = Math.cos((deg * Math.PI) / 180);
  let p: number[] = [];
  for (let i = 0; i + 1 < pts.length; i += 2) {
    const l = p.length;
    if (l >= 2 && Math.abs(pts[i]! - p[l - 2]!) < KEY && Math.abs(pts[i + 1]! - p[l - 1]!) < KEY) continue;
    p.push(pts[i]!, pts[i + 1]!);
  }
  const keep = (i: number, n: number): boolean => {
    const a = (i + n - 1) % n, c = (i + 1) % n;
    const ux = p[i * 2]! - p[a * 2]!, uy = p[i * 2 + 1]! - p[a * 2 + 1]!;
    const vx = p[c * 2]! - p[i * 2]!, vy = p[c * 2 + 1]! - p[i * 2 + 1]!;
    const lu = Math.hypot(ux, uy), lv = Math.hypot(vx, vy);
    if (lu < KEY || lv < KEY) return false;
    return (ux * vx + uy * vy) / (lu * lv) < cos;
  };
  for (let pass = 0; pass < 2; pass++) {
    const n = p.length / 2;
    if (n < 3) break;
    const out: number[] = [];
    for (let i = 0; i < n; i++) {
      if (!closed && (i === 0 || i === n - 1)) { out.push(p[i * 2]!, p[i * 2 + 1]!); continue; }
      if (keep(i, n)) out.push(p[i * 2]!, p[i * 2 + 1]!);
    }
    if (out.length < (closed ? 6 : 4)) break;
    p = out;
  }
  return p;
}

export function boxOfPolys(polys: readonly Poly[]): [number, number, number, number] {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const q of polys) for (let i = 0; i + 1 < q.pts.length; i += 2) { x0 = Math.min(x0, q.pts[i]!); x1 = Math.max(x1, q.pts[i]!); y0 = Math.min(y0, q.pts[i + 1]!); y1 = Math.max(y1, q.pts[i + 1]!); }
  return [x0, y0, x1, y1];
}

/** The cut outline of one element from the segments of its slice; null when the plane misses it. */
export function cutElement(guid: string, segs: ArrayLike<number>, cls?: string): CutElement | null {
  if (segs.length < 4) return null;
  const polys = chainSegments(segs);
  if (!polys.length) return null;
  return { guid, ...(cls ? { cls } : {}), polys, box: boxOfPolys(polys) };
}

// ---------------------------------------------------------------- queries

/** Segments (x0, y0, x1, y1) of the polylines. */
export function* segmentsOf(polys: readonly Poly[]): Generator<[number, number, number, number]> {
  for (const q of polys) {
    const n = q.pts.length / 2;
    for (let i = 0; i + 1 < n; i++) yield [q.pts[i * 2]!, q.pts[i * 2 + 1]!, q.pts[i * 2 + 2]!, q.pts[i * 2 + 3]!];
    if (q.closed && n > 2) yield [q.pts[(n - 1) * 2]!, q.pts[(n - 1) * 2 + 1]!, q.pts[0]!, q.pts[1]!];
  }
}

/** Even-odd test of a point against the closed outlines of an element. False when it has none. */
export function insideCut(e: CutElement, x: number, y: number): boolean {
  if (x < e.box[0] || x > e.box[2] || y < e.box[1] || y > e.box[3]) return false;
  let c = false;
  let any = false;
  for (const q of e.polys) {
    if (!q.closed) continue;
    any = true;
    const n = q.pts.length / 2;
    for (let i = 0, j = n - 1; i < n; j = i++) {
      const xi = q.pts[i * 2]!, yi = q.pts[i * 2 + 1]!, xj = q.pts[j * 2]!, yj = q.pts[j * 2 + 1]!;
      if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c;
    }
  }
  return any ? c : true; // open outlines (a section through a non-watertight mesh): inside its box
}

/** Distance from a point to a segment. */
export function distSeg(px: number, py: number, x0: number, y0: number, x1: number, y1: number): number {
  const dx = x1 - x0, dy = y1 - y0;
  const l = dx * dx + dy * dy;
  const t = l > 0 ? Math.max(0, Math.min(1, ((px - x0) * dx + (py - y0) * dy) / l)) : 0;
  return Math.hypot(px - (x0 + t * dx), py - (y0 + t * dy));
}

/** Distance from a point to the outlines of an element (0 inside a closed outline). */
export function distCut(e: CutElement, x: number, y: number): number {
  if (insideCut(e, x, y) && e.polys.some((q) => q.closed)) return 0;
  let best = Infinity;
  for (const s of segmentsOf(e.polys)) best = Math.min(best, distSeg(x, y, s[0], s[1], s[2], s[3]));
  return best;
}

export function pointInPolygon(x: number, y: number, poly: ArrayLike<number>): boolean {
  let c = false;
  const n = poly.length / 2;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const xi = poly[i * 2]!, yi = poly[i * 2 + 1]!, xj = poly[j * 2]!, yj = poly[j * 2 + 1]!;
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c;
  }
  return c;
}

function segCross(ax: number, ay: number, bx: number, by: number, cx: number, cy: number, dx: number, dy: number): boolean {
  const d1 = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
  const d2 = (bx - ax) * (dy - ay) - (by - ay) * (dx - ax);
  const d3 = (dx - cx) * (ay - cy) - (dy - cy) * (ax - cx);
  const d4 = (dx - cx) * (by - cy) - (dy - cy) * (bx - cx);
  return d1 * d2 < 0 && d3 * d4 < 0;
}

/** True when a closed polygon (flat, plan metres) and the element's outline share any area or cross. */
export function polygonTouchesCut(poly: ArrayLike<number>, e: CutElement): boolean {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (let i = 0; i + 1 < poly.length; i += 2) { x0 = Math.min(x0, poly[i]!); x1 = Math.max(x1, poly[i]!); y0 = Math.min(y0, poly[i + 1]!); y1 = Math.max(y1, poly[i + 1]!); }
  if (x1 < e.box[0] || x0 > e.box[2] || y1 < e.box[1] || y0 > e.box[3]) return false;
  // An outline vertex inside the polygon, a polygon corner inside the element, or crossing edges.
  for (const q of e.polys) for (let i = 0; i + 1 < q.pts.length; i += 2) if (pointInPolygon(q.pts[i]!, q.pts[i + 1]!, poly)) return true;
  const n = poly.length / 2;
  for (let i = 0; i < n; i++) if (insideCut(e, poly[i * 2]!, poly[i * 2 + 1]!) && e.polys.some((q) => q.closed)) return true;
  for (const s of segmentsOf(e.polys)) {
    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n;
      if (segCross(s[0], s[1], s[2], s[3], poly[i * 2]!, poly[i * 2 + 1]!, poly[j * 2]!, poly[j * 2 + 1]!)) return true;
    }
  }
  return false;
}

export interface Snap {
  point: [number, number];
  kind: 'corner' | 'edge';
  guid: string;
  distance: number;
}

/** The nearest corner of an outline within `tol` metres of the point, else the nearest point on an edge within it, else null. */
export function snapToCut(cut: PlanCut | null | undefined, x: number, y: number, tol: number): Snap | null {
  if (!cut) return null;
  let corner: Snap | null = null;
  let edge: Snap | null = null;
  for (const e of cut.elements) {
    if (x < e.box[0] - tol || x > e.box[2] + tol || y < e.box[1] - tol || y > e.box[3] + tol) continue;
    for (const q of e.polys) {
      for (let i = 0; i + 1 < q.pts.length; i += 2) {
        const d = Math.hypot(q.pts[i]! - x, q.pts[i + 1]! - y);
        if (d <= tol && (!corner || d < corner.distance)) corner = { point: [q.pts[i]!, q.pts[i + 1]!], kind: 'corner', guid: e.guid, distance: d };
      }
    }
    for (const s of segmentsOf(e.polys)) {
      const dx = s[2] - s[0], dy = s[3] - s[1];
      const l = dx * dx + dy * dy;
      const t = l > 0 ? Math.max(0, Math.min(1, ((x - s[0]) * dx + (y - s[1]) * dy) / l)) : 0;
      const px = s[0] + t * dx, py = s[1] + t * dy;
      const d = Math.hypot(px - x, py - y);
      if (d <= tol && (!edge || d < edge.distance)) edge = { point: [px, py], kind: 'edge', guid: e.guid, distance: d };
    }
  }
  return corner ?? edge;
}
