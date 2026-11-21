// Camera path of a `cameraPath` cue: samples the camera pose at a time. Pure (number tuples).
//
// The poses are knots of a centripetal Catmull-Rom spline (positions and targets alike). Consecutive poses that are the same
// place are one knot with an arrival and a departure time (a hold). Between two knots the camera moves along the spline at a
// constant speed by arc length; at a stop (the first and last knot when the cue eases, and every hold) the speed ramps with a
// smooth sine profile, so the camera eases in and out around holds without a jump in speed at the passing knots.

import type { CameraPose, Ease, V3 } from './score';
import { Spline3 } from './spline';
import type { P3 } from './spline';

/** Duration of an ease ramp in seconds, capped at half a segment. */
export const RAMP_S = 1.4;

export interface Knot {
  pose: CameraPose;
  arrive: number;
  depart: number;
}

const SAME_EPS = 1e-6;

function samePlace(a: CameraPose, b: CameraPose): boolean {
  const d = (p: V3, q: V3): number => Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
  return d(a.position, b.position) < SAME_EPS && d(a.target, b.target) < SAME_EPS;
}

/** Fraction of the distance covered at fraction `s` of the time, with a sine speed ramp of fraction a at the start and b at the end. */
export function rampedFraction(s: number, a: number, b: number): number {
  const x = Math.min(Math.max(s, 0), 1);
  if (a <= 0 && b <= 0) return x;
  const defIn = a > 0 ? (x <= a ? x / 2 + (a / (2 * Math.PI)) * Math.sin((Math.PI * x) / a) : a / 2) : 0;
  let defOut = 0;
  if (b > 0 && x > 1 - b) {
    const y = x - (1 - b);
    defOut = y / 2 - (b / (2 * Math.PI)) * Math.sin((Math.PI * y) / b);
  }
  const total = 1 - a / 2 - b / 2;
  return Math.min(1, Math.max(0, (x - defIn - defOut) / total));
}

export interface PathOptions {
  ease?: Ease;
  /** Per pose: false switches the ease off at that stop. */
  easeAt?: boolean[];
}

export class CameraPathSampler {
  readonly knots: Knot[] = [];
  private readonly pos: Spline3;
  private readonly tgt: Spline3;
  private readonly stopStart: boolean[] = [];
  private readonly stopEnd: boolean[] = [];

  constructor(poses: readonly CameraPose[], times: readonly number[], opts: PathOptions = {}) {
    const ease = opts.ease ?? 'inOut';
    const easeIn = ease === 'in' || ease === 'inOut';
    const easeOut = ease === 'out' || ease === 'inOut';
    const stopsEase = ease !== 'linear';
    const ok = (i: number): boolean => opts.easeAt?.[i] !== false;
    const stopFlags: boolean[] = [];
    for (let i = 0; i < poses.length; i++) {
      const t = times[i] ?? times[times.length - 1] ?? 0;
      const last = this.knots[this.knots.length - 1];
      if (last && samePlace(last.pose, poses[i]!)) {
        last.depart = Math.max(last.depart, t);
        if (!ok(i)) stopFlags[this.knots.length - 1] = false;
      } else {
        this.knots.push({ pose: poses[i]!, arrive: t, depart: t });
        stopFlags[this.knots.length - 1] = ok(i);
      }
    }
    const n = this.knots.length;
    this.pos = new Spline3(this.knots.map((k) => k.pose.position as P3));
    this.tgt = new Spline3(this.knots.map((k) => k.pose.target as P3));
    // stopStart[i]: the segment leaving knot i ramps up. stopEnd[i]: the segment arriving at knot i ramps down.
    // A knot is a stop when it is held (and the cue eases), or is the first (ease in) or the last one (ease out).
    for (let i = 0; i < n; i++) {
      const k = this.knots[i]!;
      const flag = stopFlags[i] !== false;
      const held = flag && stopsEase && k.depart > k.arrive + 1e-9;
      this.stopStart[i] = held || (flag && i === 0 && easeIn);
      this.stopEnd[i] = held || (flag && i === n - 1 && easeOut);
    }
  }

  get start(): number {
    return this.knots[0]?.arrive ?? 0;
  }

  get end(): number {
    return this.knots[this.knots.length - 1]?.depart ?? 0;
  }

  /** Arc length of the position path. */
  get length(): number {
    return this.pos.length;
  }

  /** The knot parameter u (0 to n - 1) at time t. */
  paramAt(t: number): number {
    const n = this.knots.length;
    if (n <= 1) return 0;
    if (t <= this.knots[0]!.depart) return 0;
    if (t >= this.knots[n - 1]!.arrive) return n - 1;
    let i = 0;
    while (i < n - 2 && t >= this.knots[i + 1]!.arrive) i++;
    const a = this.knots[i]!;
    const b = this.knots[i + 1]!;
    if (t <= a.depart) return i;
    const dur = Math.max(b.arrive - a.depart, 1e-9);
    const s = (t - a.depart) / dur;
    const ramp = Math.min(0.5, RAMP_S / dur);
    const f = rampedFraction(s, this.stopStart[i] ? ramp : 0, this.stopEnd[i + 1] ? ramp : 0);
    // By arc length of the position path; in place (an orbit) by the knot parameter.
    const segLen = this.pos.segLen[i] ?? 0;
    const local = segLen > 1e-9 ? this.pos.localTAtFraction(i, f) : f;
    return i + local;
  }

  /** The camera pose at time t (before the start and after the end the first and last pose). */
  sample(t: number): CameraPose {
    const n = this.knots.length;
    if (n === 0) return { position: [0, 0, 0], target: [0, 0, -1] };
    const u = this.paramAt(t);
    const pose: CameraPose = { position: this.pos.at(u), target: this.tgt.at(u) };
    const i = Math.min(Math.floor(u), Math.max(n - 2, 0));
    const f = n > 1 ? u - i : 0;
    const a = this.knots[i]!.pose;
    const b = this.knots[Math.min(i + 1, n - 1)]!.pose;
    const au = a.up ?? [0, 1, 0];
    const bu = b.up ?? [0, 1, 0];
    const up: V3 = [au[0] + (bu[0] - au[0]) * f, au[1] + (bu[1] - au[1]) * f, au[2] + (bu[2] - au[2]) * f];
    const len = Math.hypot(up[0], up[1], up[2]);
    pose.up = len > 1e-9 ? [up[0] / len, up[1] / len, up[2] / len] : [0, 1, 0];
    if (a.fovDeg !== undefined || b.fovDeg !== undefined) {
      const fa = a.fovDeg ?? b.fovDeg!;
      const fb = b.fovDeg ?? a.fovDeg!;
      pose.fovDeg = fa + (fb - fa) * f;
    }
    const near = f < 0.5 ? a : b;
    if (near.ortho !== undefined) pose.ortho = near.ortho;
    return pose;
  }
}
