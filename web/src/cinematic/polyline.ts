// Dolly-along-run: order the focus elements along their port connections and build a path.
// Pure (three math only).

import { Vector3 } from 'three';

type Centres = ReadonlyMap<number, Vector3>;

/**
 * Order `ids` into a run. Port pairs (restricted to `ids`) define adjacency; the walk starts at an
 * endpoint (degree 1; the one nearest `hint` when given, else the lowest id; with no endpoint, the
 * element farthest from the centroid, or nearest `hint`) and continues to the unvisited port
 * neighbour nearest to the current element. When a branch or gap leaves no port neighbour, it falls
 * back to the nearest unvisited element by centre distance. Every id with a centre appears once.
 */
export function orderRun(ids: Iterable<number>, centres: Centres, ports: ReadonlyArray<readonly [number, number]>, hint?: Vector3): number[] {
  const set = new Set<number>();
  for (const id of ids) if (centres.has(id)) set.add(id);
  if (set.size <= 1) return [...set];

  const adj = new Map<number, Set<number>>();
  for (const id of set) adj.set(id, new Set());
  for (const [a, b] of ports) {
    if (a !== b && set.has(a) && set.has(b)) {
      adj.get(a)!.add(b);
      adj.get(b)!.add(a);
    }
  }

  const sorted = [...set].sort((a, b) => a - b);
  const centroid = new Vector3();
  for (const id of sorted) centroid.add(centres.get(id)!);
  centroid.divideScalar(sorted.length);

  const endpoints = sorted.filter((id) => adj.get(id)!.size === 1);
  let start: number;
  if (hint) {
    const cands = endpoints.length > 0 ? endpoints : sorted;
    start = argMin(cands, (id) => centres.get(id)!.distanceToSquared(hint));
  } else if (endpoints.length > 0) {
    start = endpoints[0]!;
  } else {
    start = argMin(sorted, (id) => -centres.get(id)!.distanceToSquared(centroid));
  }

  const visited = new Set<number>([start]);
  const order = [start];
  let cur = start;
  while (order.length < sorted.length) {
    const from = centres.get(cur)!;
    const portNext = [...adj.get(cur)!].filter((n) => !visited.has(n)).sort((a, b) => a - b);
    const pool = portNext.length > 0 ? portNext : sorted.filter((n) => !visited.has(n));
    const next = argMin(pool, (n) => centres.get(n)!.distanceToSquared(from));
    visited.add(next);
    order.push(next);
    cur = next;
  }
  return order;
}

function argMin(items: readonly number[], key: (id: number) => number): number {
  let best = items[0]!;
  let bestK = Infinity;
  for (const it of items) {
    const k = key(it);
    if (k < bestK) {
      bestK = k;
      best = it;
    }
  }
  return best;
}

/** A polyline with arc-length parametrisation. */
export class PolylinePath {
  readonly points: Vector3[];
  /** Cumulative length at each point; cum[0] = 0. */
  readonly cum: number[];

  constructor(points: readonly Vector3[]) {
    // Drop consecutive duplicates so every segment has length.
    const pts: Vector3[] = [];
    for (const p of points) {
      const last = pts[pts.length - 1];
      if (!last || last.distanceToSquared(p) > 1e-12) pts.push(p.clone());
    }
    this.points = pts;
    this.cum = [0];
    for (let i = 1; i < pts.length; i++) this.cum.push(this.cum[i - 1]! + pts[i]!.distanceTo(pts[i - 1]!));
  }

  get length(): number {
    return this.cum[this.cum.length - 1] ?? 0;
  }

  /** Point at arc length `s` (clamped to the path). */
  pointAt(s: number, out = new Vector3()): Vector3 {
    const n = this.points.length;
    if (n === 0) return out.set(0, 0, 0);
    if (n === 1 || s <= 0) return out.copy(this.points[0]!);
    if (s >= this.length) return out.copy(this.points[n - 1]!);
    let lo = 0;
    let hi = n - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (this.cum[mid]! <= s) lo = mid;
      else hi = mid;
    }
    const seg = this.cum[hi]! - this.cum[lo]!;
    const t = seg > 0 ? (s - this.cum[lo]!) / seg : 0;
    return out.lerpVectors(this.points[lo]!, this.points[hi]!, t);
  }
}

/** Order the run and build its path through the element centres. */
export function buildRunPath(ids: Iterable<number>, centres: Centres, ports: ReadonlyArray<readonly [number, number]>, hint?: Vector3): { order: number[]; path: PolylinePath } {
  const order = orderRun(ids, centres, ports, hint);
  return { order, path: new PolylinePath(order.map((id) => centres.get(id)!)) };
}
