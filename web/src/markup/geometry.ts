// 2D geometry of the markup shapes in pixel space: the scalloped revision cloud, ellipses, arrow heads, simplification of
// freehand paths and the rectangle helpers. Pure, no DOM. Points are flat arrays [x0, y0, x1, y1, ...].

export type Pt = readonly [number, number];

/** Signed area (shoelace) of a closed flat polygon. Positive: counter-clockwise in a y-up system. */
export function signedArea(p: ArrayLike<number>): number {
  let a = 0;
  const n = p.length / 2;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    a += p[2 * i]! * p[2 * j + 1]! - p[2 * j]! * p[2 * i + 1]!;
  }
  return a / 2;
}

export function perimeter(p: ArrayLike<number>, closed: boolean): number {
  const n = p.length / 2;
  let l = 0;
  for (let i = 0; i < (closed ? n : n - 1); i++) {
    const j = (i + 1) % n;
    l += Math.hypot(p[2 * j]! - p[2 * i]!, p[2 * j + 1]! - p[2 * i + 1]!);
  }
  return l;
}

export function pointInPolygon(x: number, y: number, p: ArrayLike<number>): boolean {
  let inside = false;
  const n = p.length / 2;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const xi = p[2 * i]!, yi = p[2 * i + 1]!, xj = p[2 * j]!, yj = p[2 * j + 1]!;
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Corners of the rectangle given by 2 opposite points, as a closed flat polygon. */
export function rectCorners(a: Pt, b: Pt): number[] {
  return [a[0], a[1], b[0], a[1], b[0], b[1], a[0], b[1]];
}

/** Flat polygon of an ellipse inscribed in the box of 2 opposite points. */
export function ellipsePoints(a: Pt, b: Pt, n = 56): number[] {
  const cx = (a[0] + b[0]) / 2, cy = (a[1] + b[1]) / 2;
  const rx = Math.abs(b[0] - a[0]) / 2, ry = Math.abs(b[1] - a[1]) / 2;
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const t = (i / n) * Math.PI * 2;
    out.push(cx + rx * Math.cos(t), cy + ry * Math.sin(t));
  }
  return out;
}

/** Resample a closed flat polygon into `n` points equally spaced along its perimeter (the first point stays). */
export function resampleClosed(p: ArrayLike<number>, n: number): number[] {
  const m = p.length / 2;
  const total = perimeter(p, true);
  if (m < 2 || total < 1e-9 || n < 1) return Array.from(p);
  const step = total / n;
  const out: number[] = [];
  let seg = 0;
  let segStart = 0; // arc length at the start of segment `seg`
  let segLen = Math.hypot(p[2]! - p[0]!, p[3]! - p[1]!);
  for (let k = 0; k < n; k++) {
    const d = k * step;
    while (seg < m - 1 && d > segStart + segLen + 1e-12) {
      segStart += segLen;
      seg++;
      const j = (seg + 1) % m;
      segLen = Math.hypot(p[2 * j]! - p[2 * seg]!, p[2 * j + 1]! - p[2 * seg + 1]!);
    }
    const j = (seg + 1) % m;
    const t = segLen > 1e-12 ? (d - segStart) / segLen : 0;
    out.push(p[2 * seg]! + (p[2 * j]! - p[2 * seg]!) * t, p[2 * seg + 1]! + (p[2 * j + 1]! - p[2 * seg + 1]!) * t);
  }
  return out;
}

export interface CloudOptions {
  /** Wanted scallop length (chord), px. The real length is the perimeter divided by a whole number of scallops. */
  arc: number;
  /** Bulge of each scallop as a fraction of its chord (0.5 is a semicircle). Default 0.42. */
  bulge?: number;
  /** Points per scallop (default 9, the two ends included). */
  steps?: number;
}

/**
 * The outline of a revision cloud around a closed flat polygon: the polygon is resampled into scallops of about `arc` px
 * and each chord is replaced by a circular arc that bulges outward. Returns a closed flat polyline (the last point is the
 * first scallop's start, not repeated). A polygon with fewer than 3 corners or no area returns its points.
 */
export function cloudOutline(poly: ArrayLike<number>, o: CloudOptions): number[] {
  const area = signedArea(poly);
  const per = perimeter(poly, true);
  if (poly.length < 6 || Math.abs(area) < 1e-6 || per < 1e-6) return Array.from(poly);
  const n = Math.max(3, Math.round(per / Math.max(2, o.arc)));
  const q = resampleClosed(poly, n);
  const sign = area > 0 ? 1 : -1;
  const bulge = o.bulge ?? 0.42;
  const steps = Math.max(3, o.steps ?? 9);
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    const ax = q[2 * i]!, ay = q[2 * i + 1]!, bx = q[2 * j]!, by = q[2 * j + 1]!;
    const dx = bx - ax, dy = by - ay;
    const c = Math.hypot(dx, dy);
    if (c < 1e-9) { out.push(ax, ay); continue; }
    // Outward normal: right of the edge for a positive area (interior on the left).
    const nx = (dy / c) * sign, ny = (-dx / c) * sign;
    const h = bulge * c;
    const mx = (ax + bx) / 2, my = (ay + by) / 2;
    // Circle through A, B with sagitta h towards (nx, ny): the centre lies on the opposite side of the chord.
    const R = (c * c / 4 + h * h) / (2 * h);
    const cx = mx + nx * (h - R), cy = my + ny * (h - R);
    const a0 = Math.atan2(ay - cy, ax - cx);
    let da = Math.atan2(by - cy, bx - cx) - a0;
    // The arc through the outward apex: choose the direction whose middle point lies on the outward side.
    const mid0 = a0 + da / 2;
    const mdx = cx + R * Math.cos(mid0) - mx, mdy = cy + R * Math.sin(mid0) - my;
    if (mdx * nx + mdy * ny < 0) da += da > 0 ? -2 * Math.PI : 2 * Math.PI;
    for (let s = 0; s < steps - 1; s++) {
      const a = a0 + (da * s) / (steps - 1);
      out.push(cx + R * Math.cos(a), cy + R * Math.sin(a));
    }
  }
  return out;
}

/** The closed polygon (pixels) a cloud is built on: 2 points are opposite corners, 3 or more are a freehand outline. */
export function cloudBase(points: ReadonlyArray<Pt>): number[] {
  if (points.length === 2) return rectCorners(points[0]!, points[1]!);
  return points.flatMap((p) => [p[0], p[1]]);
}

/** Douglas-Peucker simplification of a flat open polyline; endpoints stay. */
export function simplify(p: ArrayLike<number>, tol: number): number[] {
  const n = p.length / 2;
  if (n <= 2) return Array.from(p);
  const keep = new Uint8Array(n);
  keep[0] = keep[n - 1] = 1;
  const stack: Array<[number, number]> = [[0, n - 1]];
  while (stack.length) {
    const [a, b] = stack.pop()!;
    let md = -1, mi = -1;
    const ax = p[2 * a]!, ay = p[2 * a + 1]!, bx = p[2 * b]!, by = p[2 * b + 1]!;
    const dx = bx - ax, dy = by - ay;
    const l2 = dx * dx + dy * dy;
    for (let i = a + 1; i < b; i++) {
      const px = p[2 * i]!, py = p[2 * i + 1]!;
      const t = l2 > 0 ? Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / l2)) : 0;
      const d = Math.hypot(px - (ax + t * dx), py - (ay + t * dy));
      if (d > md) { md = d; mi = i; }
    }
    if (md > tol && mi > 0) {
      keep[mi] = 1;
      stack.push([a, mi], [mi, b]);
    }
  }
  const out: number[] = [];
  for (let i = 0; i < n; i++) if (keep[i]) out.push(p[2 * i]!, p[2 * i + 1]!);
  return out;
}

/** The 3 points of an arrow head whose tip is (x2, y2), for a line from (x1, y1). Null when the line is a dot. */
export function arrowHead(x1: number, y1: number, x2: number, y2: number, len: number, half: number): number[] | null {
  const l = Math.hypot(x2 - x1, y2 - y1);
  if (l < 1e-6) return null;
  const ux = (x2 - x1) / l, uy = (y2 - y1) / l;
  const hl = Math.min(len, l * 0.8);
  const bx = x2 - ux * hl, by = y2 - uy * hl;
  return [x2, y2, bx - uy * half, by + ux * half, bx + uy * half, by - ux * half];
}

export function bounds(p: ArrayLike<number>): { x0: number; y0: number; x1: number; y1: number } {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (let i = 0; i < p.length; i += 2) {
    x0 = Math.min(x0, p[i]!); x1 = Math.max(x1, p[i]!);
    y0 = Math.min(y0, p[i + 1]!); y1 = Math.max(y1, p[i + 1]!);
  }
  return { x0, y0, x1, y1 };
}

/** Distance from a point to a polyline (flat), optionally closed. */
export function distToPolyline(x: number, y: number, p: ArrayLike<number>, closed: boolean): number {
  const n = p.length / 2;
  let best = Infinity;
  for (let i = 0; i < (closed ? n : n - 1); i++) {
    const j = (i + 1) % n;
    const ax = p[2 * i]!, ay = p[2 * i + 1]!, bx = p[2 * j]!, by = p[2 * j + 1]!;
    const dx = bx - ax, dy = by - ay;
    const l2 = dx * dx + dy * dy;
    const t = l2 > 0 ? Math.max(0, Math.min(1, ((x - ax) * dx + (y - ay) * dy) / l2)) : 0;
    best = Math.min(best, Math.hypot(x - (ax + t * dx), y - (ay + t * dy)));
  }
  return best;
}

/**
 * A scalloped open line from (x0, y0) to (x1, y1): the chord is split into scallops of about `arc` px and each is replaced by
 * a circular arc that bulges to the side of `(sx, sy)` (a direction, usually away from the middle of the shape). Used for the
 * edges of a region box. Returns a flat polyline that ends on the last point.
 */
export function scallopLine(x0: number, y0: number, x1: number, y1: number, arc: number, sx: number, sy: number, bulge = 0.4, steps = 7): number[] {
  const L = Math.hypot(x1 - x0, y1 - y0);
  if (L < 1e-6) return [x0, y0, x1, y1];
  const n = Math.max(1, Math.round(L / Math.max(2, arc)));
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const ax = x0 + ((x1 - x0) * i) / n, ay = y0 + ((y1 - y0) * i) / n;
    const bx = x0 + ((x1 - x0) * (i + 1)) / n, by = y0 + ((y1 - y0) * (i + 1)) / n;
    const dx = bx - ax, dy = by - ay;
    const c = Math.hypot(dx, dy);
    let nx = dy / c, ny = -dx / c;
    if (nx * sx + ny * sy < 0) { nx = -nx; ny = -ny; }
    const h = bulge * c;
    const R = (c * c / 4 + h * h) / (2 * h);
    const mx = (ax + bx) / 2, my = (ay + by) / 2;
    const cx = mx + nx * (h - R), cy = my + ny * (h - R);
    const a0 = Math.atan2(ay - cy, ax - cx);
    let da = Math.atan2(by - cy, bx - cx) - a0;
    const mid = a0 + da / 2;
    if ((cx + R * Math.cos(mid) - mx) * nx + (cy + R * Math.sin(mid) - my) * ny < 0) da += da > 0 ? -2 * Math.PI : 2 * Math.PI;
    for (let k = 0; k < steps; k++) {
      const a = a0 + (da * k) / (steps - 1);
      out.push(cx + R * Math.cos(a), cy + R * Math.sin(a));
    }
  }
  out.push(x1, y1);
  return out;
}

/** Convex hull of flat points (monotone chain), as a flat closed polygon. */
export function convexHull(p: ArrayLike<number>): number[] {
  const pts: Array<[number, number]> = [];
  for (let i = 0; i < p.length; i += 2) pts.push([p[i]!, p[i + 1]!]);
  pts.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (pts.length < 3) return pts.flat();
  const cross = (o: [number, number], a: [number, number], b: [number, number]): number => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lo: Array<[number, number]> = [];
  for (const q of pts) { while (lo.length >= 2 && cross(lo[lo.length - 2]!, lo[lo.length - 1]!, q) <= 0) lo.pop(); lo.push(q); }
  const up: Array<[number, number]> = [];
  for (const q of [...pts].reverse()) { while (up.length >= 2 && cross(up[up.length - 2]!, up[up.length - 1]!, q) <= 0) up.pop(); up.push(q); }
  lo.pop(); up.pop();
  return [...lo, ...up].flat();
}
