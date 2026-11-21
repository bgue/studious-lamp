// Centripetal Catmull-Rom spline through 3D points (alpha 0.5, Barry-Goldman evaluation). Pure: plain number tuples, no three.js.
// The curve passes through every point exactly, has no cusps or loops and does not overshoot on unevenly spaced points the way
// the uniform form does. The ends use a mirrored phantom point, so the first and last segment leave the end point cleanly.
// `Spline3` also reparametrises each segment by arc length, so a player can move at constant speed along the path.

export type P3 = [number, number, number];

const EPS = 1e-9;
/** Samples per segment in the arc-length table. */
export const ARC_SAMPLES = 24;

function sub(a: P3, b: P3): P3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}
function dist(a: P3, b: P3): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}
function mix(a: P3, b: P3, wa: number, wb: number): P3 {
  return [a[0] * wa + b[0] * wb, a[1] * wa + b[1] * wb, a[2] * wa + b[2] * wb];
}

/** The point at `t` in [0, 1] of the segment p1 to p2 (p0 and p3 are the neighbours). t = 0 gives p1 and t = 1 gives p2 exactly. */
export function centripetal(p0: P3, p1: P3, p2: P3, p3: P3, t: number, alpha = 0.5): P3 {
  if (t <= 0) return [p1[0], p1[1], p1[2]];
  if (t >= 1) return [p2[0], p2[1], p2[2]];
  const k = (a: P3, b: P3): number => Math.pow(Math.max(dist(a, b), EPS), alpha);
  const t0 = 0;
  const t1 = t0 + k(p0, p1);
  const t2 = t1 + k(p1, p2);
  const t3 = t2 + k(p2, p3);
  const u = t1 + (t2 - t1) * t;
  const lerp = (a: P3, b: P3, ta: number, tb: number): P3 => mix(a, b, (tb - u) / (tb - ta), (u - ta) / (tb - ta));
  const a1 = lerp(p0, p1, t0, t1);
  const a2 = lerp(p1, p2, t1, t2);
  const a3 = lerp(p2, p3, t2, t3);
  const b1 = lerp(a1, a2, t0, t2);
  const b2 = lerp(a2, a3, t1, t3);
  return lerp(b1, b2, t1, t2);
}

export class Spline3 {
  readonly pts: P3[];
  /** Arc length of each segment (n - 1 values). */
  readonly segLen: number[] = [];
  /** Cumulative arc length at ARC_SAMPLES + 1 samples of each segment. */
  private readonly table: number[][] = [];

  constructor(points: readonly P3[], readonly alpha = 0.5) {
    this.pts = points.map((p) => [p[0], p[1], p[2]] as P3);
    for (let i = 0; i < this.pts.length - 1; i++) {
      const cum = [0];
      let prev = this.segmentAt(i, 0);
      for (let k = 1; k <= ARC_SAMPLES; k++) {
        const p = this.segmentAt(i, k / ARC_SAMPLES);
        cum.push(cum[k - 1]! + dist(prev, p));
        prev = p;
      }
      this.table.push(cum);
      this.segLen.push(cum[ARC_SAMPLES]!);
    }
  }

  get count(): number {
    return this.pts.length;
  }

  get length(): number {
    return this.segLen.reduce((a, b) => a + b, 0);
  }

  private neighbour(i: number): P3 {
    const n = this.pts.length;
    if (i < 0) return n > 1 ? sub(mix(this.pts[0]!, this.pts[0]!, 2, 0), this.pts[1]!) : this.pts[0]!;
    if (i >= n) return n > 1 ? sub(mix(this.pts[n - 1]!, this.pts[n - 1]!, 2, 0), this.pts[n - 2]!) : this.pts[n - 1]!;
    return this.pts[i]!;
  }

  /** Point on segment i (between pts[i] and pts[i + 1]) at local t in [0, 1]. */
  segmentAt(i: number, t: number): P3 {
    const n = this.pts.length;
    if (n === 0) return [0, 0, 0];
    if (n === 1) return [...this.pts[0]!] as P3;
    const s = Math.min(Math.max(i, 0), n - 2);
    return centripetal(this.neighbour(s - 1), this.pts[s]!, this.pts[s + 1]!, this.neighbour(s + 2), t, this.alpha);
  }

  /** Point at the knot parameter u in [0, n - 1] (an integer u is a point). */
  at(u: number): P3 {
    const n = this.pts.length;
    if (n <= 1) return this.segmentAt(0, 0);
    const c = Math.min(Math.max(u, 0), n - 1);
    const i = Math.min(Math.floor(c), n - 2);
    return this.segmentAt(i, c - i);
  }

  /** Local t of segment i where the arc length from the segment start is the fraction f (0..1) of the segment length. */
  localTAtFraction(i: number, f: number): number {
    const cum = this.table[Math.min(Math.max(i, 0), this.table.length - 1)];
    if (!cum) return f;
    const total = cum[ARC_SAMPLES]!;
    if (total < EPS) return f;
    const target = Math.min(Math.max(f, 0), 1) * total;
    let lo = 0;
    let hi = ARC_SAMPLES;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (cum[mid]! <= target) lo = mid;
      else hi = mid;
    }
    const span = cum[hi]! - cum[lo]!;
    const frac = span < EPS ? 0 : (target - cum[lo]!) / span;
    return (lo + frac) / ARC_SAMPLES;
  }
}
