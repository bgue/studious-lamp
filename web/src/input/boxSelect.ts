// Box (rubber band) selection geometry: pure maths over the world bounding boxes of the elements, no DOM and no three.js.
//
// The CAD convention: a box dragged from left to right is a WINDOW and picks the elements that lie fully inside it; a box
// dragged from right to left is a CROSSING box and picks every element it touches. An element is its world bounding box
// (a conservative stand-in for its shape), projected to the screen: the 8 corners for a window, the convex hull of the
// 8 corners (clipped at the near plane) for a crossing, so a box that lies inside a big wall still picks the wall.
// 5000 elements take well under a millisecond: nothing is drawn or raycast.

export type BoxMode = 'window' | 'crossing';

export interface PixelRect {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

/** The rectangle between two drag points, with x0 <= x1 and y0 <= y1. */
export function rectOf(ax: number, ay: number, bx: number, by: number): PixelRect {
  return { x0: Math.min(ax, bx), y0: Math.min(ay, by), x1: Math.max(ax, bx), y1: Math.max(ay, by) };
}

/** Left to right is a window, right to left is a crossing. A drag with no horizontal travel is a window. */
export function boxModeOf(startX: number, endX: number): BoxMode {
  return endX >= startX ? 'window' : 'crossing';
}

export interface BoxQuery {
  /** Number of elements; ids are 0..count-1. */
  count: number;
  /** World bounds [minx, miny, minz, maxx, maxy, maxz] of an element, or null when it has none. */
  boundsOf(id: number): ArrayLike<number> | null | undefined;
  /** False for hidden, isolated-away and click-through elements. */
  eligible(id: number): boolean;
  /** Column-major projection * view matrix (three's Matrix4.elements). */
  viewProj: ArrayLike<number>;
  /** Canvas size in CSS pixels. */
  width: number;
  height: number;
  rect: PixelRect;
  mode: BoxMode;
  /** Clip-space w of the near plane (the camera's near distance for a perspective camera). Default 1e-4. */
  nearW?: number;
}

type P2 = [number, number];

/** Ids of the elements a box picks, in id order. */
export function pickInRect(q: BoxQuery): number[] {
  const out: number[] = [];
  const m = q.viewProj;
  const eps = q.nearW ?? 1e-4;
  const { x0, y0, x1, y1 } = q.rect;
  const cx: number[] = new Array(8);
  const cy: number[] = new Array(8);
  const cw: number[] = new Array(8);
  const px: number[] = new Array(8);
  const py: number[] = new Array(8);
  for (let id = 0; id < q.count; id++) {
    const b = q.boundsOf(id);
    if (!b || !q.eligible(id)) continue;
    let front = 0;
    for (let i = 0; i < 8; i++) {
      const x = i & 1 ? b[3]! : b[0]!;
      const y = i & 2 ? b[4]! : b[1]!;
      const z = i & 4 ? b[5]! : b[2]!;
      const w = m[3]! * x + m[7]! * y + m[11]! * z + m[15]!;
      cx[i] = m[0]! * x + m[4]! * y + m[8]! * z + m[12]!;
      cy[i] = m[1]! * x + m[5]! * y + m[9]! * z + m[13]!;
      cw[i] = w;
      if (w > eps) {
        front++;
        px[i] = (cx[i]! / w * 0.5 + 0.5) * q.width;
        py[i] = (1 - (cy[i]! / w * 0.5 + 0.5)) * q.height;
      }
    }
    if (front === 0) continue;
    if (q.mode === 'window') {
      if (front < 8) continue;
      let inside = true;
      for (let i = 0; i < 8 && inside; i++) inside = px[i]! >= x0 && px[i]! <= x1 && py[i]! >= y0 && py[i]! <= y1;
      if (inside) out.push(id);
    } else if (crossingHit(cx, cy, cw, px, py, eps, q)) out.push(id);
  }
  return out;
}

const EDGES: ReadonlyArray<readonly [number, number]> = [
  [0, 1], [2, 3], [4, 5], [6, 7], [0, 2], [1, 3], [4, 6], [5, 7], [0, 4], [1, 5], [2, 6], [3, 7],
];

function crossingHit(cx: number[], cy: number[], cw: number[], px: number[], py: number[], eps: number, q: BoxQuery): boolean {
  const { x0, y0, x1, y1 } = q.rect;
  const pts: P2[] = [];
  const segs: Array<[P2, P2]> = [];
  for (let i = 0; i < 8; i++) if (cw[i]! > eps) pts.push([px[i]!, py[i]!]);
  for (const [a, b] of EDGES) {
    const fa = cw[a]! > eps;
    const fb = cw[b]! > eps;
    if (!fa && !fb) continue;
    let pa: P2 = [px[a]!, py[a]!];
    let pb: P2 = [px[b]!, py[b]!];
    if (fa !== fb) {
      // Clip the edge at the near plane: the point where w = eps.
      const t = (eps - cw[a]!) / (cw[b]! - cw[a]!);
      const x = cx[a]! + t * (cx[b]! - cx[a]!);
      const y = cy[a]! + t * (cy[b]! - cy[a]!);
      const c: P2 = [(x / eps * 0.5 + 0.5) * q.width, (1 - (y / eps * 0.5 + 0.5)) * q.height];
      pts.push(c);
      if (fa) pb = c;
      else pa = c;
    }
    segs.push([pa, pb]);
  }
  // Bounding box of the projection against the rectangle: the quick reject.
  let minx = Infinity;
  let miny = Infinity;
  let maxx = -Infinity;
  let maxy = -Infinity;
  for (const p of pts) {
    if (p[0] < minx) minx = p[0];
    if (p[0] > maxx) maxx = p[0];
    if (p[1] < miny) miny = p[1];
    if (p[1] > maxy) maxy = p[1];
    if (p[0] >= x0 && p[0] <= x1 && p[1] >= y0 && p[1] <= y1) return true;
  }
  if (maxx < x0 || minx > x1 || maxy < y0 || miny > y1) return false;
  for (const [a, b] of segs) if (segmentTouchesRect(a, b, q.rect)) return true;
  // Neither a corner nor an edge is in the rectangle: the rectangle may lie inside the projected shape.
  const hull = convexHull(pts);
  return hull.length >= 3 && insideConvex(hull, (x0 + x1) / 2, (y0 + y1) / 2);
}

/** Liang-Barsky: does the segment touch the rectangle? */
export function segmentTouchesRect(a: P2, b: P2, r: PixelRect): boolean {
  let t0 = 0;
  let t1 = 1;
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const clip = (p: number, qv: number): boolean => {
    if (p === 0) return qv >= 0;
    const t = qv / p;
    if (p < 0) {
      if (t > t1) return false;
      if (t > t0) t0 = t;
    } else {
      if (t < t0) return false;
      if (t < t1) t1 = t;
    }
    return true;
  };
  return clip(-dx, a[0] - r.x0) && clip(dx, r.x1 - a[0]) && clip(-dy, a[1] - r.y0) && clip(dy, r.y1 - a[1]);
}

/** Convex hull, counter-clockwise (Andrew's monotone chain). */
export function convexHull(points: P2[]): P2[] {
  const p = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (p.length < 3) return p;
  const cross = (o: P2, a: P2, b: P2): number => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower: P2[] = [];
  for (const pt of p) {
    while (lower.length >= 2 && cross(lower[lower.length - 2]!, lower[lower.length - 1]!, pt) <= 0) lower.pop();
    lower.push(pt);
  }
  const upper: P2[] = [];
  for (let i = p.length - 1; i >= 0; i--) {
    const pt = p[i]!;
    while (upper.length >= 2 && cross(upper[upper.length - 2]!, upper[upper.length - 1]!, pt) <= 0) upper.pop();
    upper.push(pt);
  }
  lower.pop();
  upper.pop();
  return lower.concat(upper);
}

// Pixel space has y down, so the hull above is clockwise on screen: the sign test below follows the monotone-chain order
// as computed (counter-clockwise in the plain x-right, y-up reading of the numbers).
function insideConvex(hull: P2[], x: number, y: number): boolean {
  for (let i = 0; i < hull.length; i++) {
    const a = hull[i]!;
    const b = hull[(i + 1) % hull.length]!;
    if ((b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0]) < 0) return false;
  }
  return true;
}
