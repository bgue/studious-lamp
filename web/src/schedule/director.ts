// The 4D camera director: reads a 4D plan and the bounding boxes of the model and decides, for every stretch of the film, where the camera
// goes, when the building explodes, where a section box clips, what is captioned and which activities are labelled. It emits normal score
// cues (src/anim/score.ts) in video seconds that sit on top of a `schedule4d` cue covering the film, and one line of explanation per
// decision. Design: docs/design/4d-xer-animation.md section 5. Pure and deterministic: no DOM, no clock, no random numbers; the same plan,
// model and options give the same cues.
//
// The rules (the numbers are the defaults of DirectorOptions):
//  * The film is sampled every `step` (0.5 s). At each sample the interest set is the elements that are active during the next `window`
//    seconds (the active ones plus those about to start), the ones that change state in that window weighing three times as much.
//  * Interest region = the box of the interest set without the outer 5 % (weighted) when there are 20 or more elements. Shot: wide when
//    the region diagonal is 55 % of the model's or more (frame everything), medium from 20 %, close below. Moves are `camera` cues with
//    `{frame}`; a shot lasts at least `minShot` (4 s); a new shot only when the type changes or the region moved by more than its own size.
//  * Comfort: the camera never moves while the building explodes or collapses; camera moves start at least 3 s apart (a shot is 4 s at
//    least); in a gap of 8 s or more with no move, a slow orbit. Style `fixed` and `none` emit no camera cues at all.
//  * Explode when the interest set is on 3 or more storeys at once (a 2-storey model: both storeys have work and the upper storey roofs
//    over the lower work), when that holds for 6 s or more; collapse when work concentrates again. A run of 6 s or more gets an explode
//    (2 s), a hold and a collapse (2 s). At up to 3 phase milestones (style.explode `auto`), an explode-and-orbit beat of 11.6 s.
//  * Each floor apart (style.explode `floor`): the milestone beats and the work-spread explode are off. When the active work moves onto a
//    storey (the storey with most of the elements going up now, for 6 s or more; gaps of up to 6 s with no work keep the run), the storeys
//    ease apart (2 s), that storey's elements are the x-ray focus (the rest is context), a caption names the floor, the building stays
//    apart while that floor's work runs and collapses (2 s) before the work moves to the next floor (1 s of rest between a collapse and
//    the next explode). The camera takes a wide shot of the apart building after the explode and waits during explode and collapse.
//  * Section box (style.sectionBox `auto`): when all active work, for 6 s or more, sits on one storey and inside the envelope (inside that
//    storey's footprint, not on its edge): a box around the storey; off (or the next storey) when work leaves.
//  * Focus: the schedule4d runner follows the active elements itself (style.xrayFocus). `focus` cues only mark a beat on the whole building.
//  * Captions at each milestone (style.captions), merged when several fall on one moment, and one at the start; at most `style.labels`
//    activity labels at once, on the largest active activities, each shown for 3 to 8 s.

import type { Cue } from '../anim/score';
import { mapSpan, planTimeAt, secondsAtPlan } from '../anim/fourd/timeline';
import type { BBox } from './model';
import type { FourDPlan } from './types';

/** What the director needs of the model: element boxes (IFC frame, Z up) and storeys by GlobalId. A FourDModel fits. */
export interface DirectorModel {
  elements: ReadonlyArray<{ globalId: string; bbox?: BBox; storey?: string }>;
  /** Storeys with elevations (m); absent: derived from the element boxes. */
  storeys?: ReadonlyArray<{ name: string; elevation: number }>;
}

export interface DirectorOptions {
  /** calm: longer shots and slower moves; dynamic (default): 4 s shots. */
  profile?: 'calm' | 'dynamic';
  /** Video second at which the schedule4d cue starts (default 0) and its length (default: the time map's span). */
  start?: number;
  duration?: number;
  /** Sampling step, seconds (0.5). */
  step?: number;
  /** Shortest shot, seconds (profile: 4 or 6). */
  minShot?: number;
  /** Seconds all active work must stay on one storey, inside the envelope, for a section box (6). */
  sectionSeconds?: number;
  /** Explode from this many storeys with work at once (3). */
  explodeStoreys?: number;
  /** Most explode beats at phase milestones (3); 0 = none. */
  maxBeats?: number;
  /** At most this many labels at once; overrides style.labels. */
  labels?: number;
}

export interface DirectorResult {
  cues: Cue[];
  /** One line per decision, with the time and the date. */
  notes: string[];
  /** Video second (in the film, absolute) of each note, for placing the lines in a script. */
  noteTimes: number[];
  /** Film length in seconds from `start`, with the finale (absent: no finale, the film ends where the plan does). */
  duration?: number;
}

interface Profile {
  minShot: number;
  window: number;
  moveScale: number;
  orbitDegPerS: number;
}
const PROFILES: Record<'calm' | 'dynamic', Profile> = {
  dynamic: { minShot: 4, window: 4, moveScale: 1, orbitDegPerS: 4 },
  calm: { minShot: 6, window: 6, moveScale: 1.3, orbitDegPerS: 2.5 },
};

const MARGIN = { wide: 1.3, medium: 1.9, close: 1.6 } as const;
type ShotType = 'wide' | 'medium' | 'close';
const EXPLODE_FACTOR = 1.5;
const EXPLODE_S = 2;
const COLLAPSE_S = 2;
const SECTION_IN_S = 1.5;
const SECTION_OUT_S = 1;
const LABEL_MIN_S = 3;
const LABEL_MAX_S = 8;
const LABEL_FIELDS = ['activity', 'percent', 'finish'];
const PHASE_WORDS = /complete|closed|weathertight|topping|top-out|enclosed|finish|handover|shell|frame|envelope|roof|structure/i;
const FLOOR_HOLD_MIN_S = 4;
const FLOOR_GAP_S = 6;
const FLOOR_REST_S = 1;
const FLOOR_CAPTION_S = 4;
const DOLLY_S = 6;
const FINALE_ORBIT_S = 8;
const FINALE_ORBIT_DEG = 90;
const DOLLY_MARGIN = 1.08;
/** Seconds the finale adds after the last work (the collapse of a building still apart not counted). */
export function finaleSeconds(finale: 'none' | 'dolly' | 'orbit' | undefined): number {
  return finale === 'dolly' ? DOLLY_S + FINALE_ORBIT_S : finale === 'orbit' ? FINALE_ORBIT_S : 0;
}
const BEAT = { explode: 0, wide: 2, orbit: 5, orbitS: 4.5, collapse: 9.6, end: 11.6 };

const r3 = (n: number): number => Math.round(n * 1000) / 1000;
/** 2027-05-21 from plan ms. */
export function isoDate(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

const mmss = (t: number): string => {
  const m = Math.floor(t / 60);
  const s = t - m * 60;
  return `${String(m).padStart(2, '0')}:${s.toFixed(1).padStart(4, '0')}`;
};

type Range = [number, number];

/** Parts of `runs` outside every blocker range. */
function subtract(runs: Range[], blockers: Range[]): Range[] {
  let out = runs.slice();
  for (const [b0, b1] of blockers) {
    const next: Range[] = [];
    for (const [a, b] of out) {
      if (b1 <= a || b0 >= b) next.push([a, b]);
      else {
        if (b0 > a) next.push([a, b0]);
        if (b1 < b) next.push([b1, b]);
      }
    }
    out = next;
  }
  return out;
}

const overlaps = (a0: number, a1: number, b0: number, b1: number): boolean => a0 < b1 - 1e-9 && a1 > b0 + 1e-9;

/** Join runs that are closer than `gap`. */
function mergeRuns(runs: Range[], gap: number): Range[] {
  const out: Range[] = [];
  for (const r of runs) {
    const last = out[out.length - 1];
    if (last && r[0] - last[1] <= gap) last[1] = Math.max(last[1], r[1]);
    else out.push([r[0], r[1]]);
  }
  return out;
}

interface Seg {
  from: number;
  to: number;
  task: string;
}

interface G {
  gid: string;
  box: BBox;
  c: [number, number, number];
  storey: number;
  segs: Seg[];
}

interface Region {
  box: BBox;
  ids: string[];
  c: [number, number, number];
  diag: number;
  n: number;
}

const diagOf = (b: BBox): number => Math.hypot(b[3] - b[0], b[4] - b[1], b[5] - b[2]);

function weightedQuantiles(vals: number[], w: number[], lo: number, hi: number): [number, number] {
  const idx = vals.map((_, i) => i).sort((a, b) => vals[a]! - vals[b]! || a - b);
  let total = 0;
  for (const i of idx) total += w[i]!;
  let acc = 0;
  let a = vals[idx[0]!]!;
  let b = vals[idx[idx.length - 1]!]!;
  let gotLo = false;
  for (const i of idx) {
    acc += w[i]!;
    if (!gotLo && acc >= lo * total) {
      a = vals[i]!;
      gotLo = true;
    }
    if (acc >= hi * total) {
      b = vals[i]!;
      break;
    }
  }
  return [a, b];
}

/** The box of a set without its outer 5 % (weighted, when 20 or more), and the elements that reach each side of it. */
function regionOf(gs: G[], idxs: number[], w: number[]): Region | null {
  if (idxs.length === 0) return null;
  let keep = idxs;
  if (idxs.length >= 20) {
    const ws = idxs.map((i) => w[i]!);
    const rng = [0, 1, 2].map((ax) => weightedQuantiles(idxs.map((i) => gs[i]!.c[ax]!), ws, 0.05, 0.95));
    const k = idxs.filter((i) => [0, 1, 2].every((ax) => gs[i]!.c[ax]! >= rng[ax]![0] && gs[i]!.c[ax]! <= rng[ax]![1]));
    if (k.length > 0) keep = k;
  }
  const box: BBox = [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity];
  for (const i of keep) {
    const b = gs[i]!.box;
    for (let a = 0; a < 3; a++) {
      if (b[a]! < box[a]!) box[a] = b[a]!;
      if (b[a + 3]! > box[a + 3]!) box[a + 3] = b[a + 3]!;
    }
  }
  // the elements that reach the sides of the box: framing them frames the box
  const pick: number[] = [];
  for (let s = 0; s < 6; s++) {
    let best = keep[0]!;
    for (const i of keep) {
      const b = gs[i]!.box;
      const better = s < 3 ? b[s]! < gs[best]!.box[s]! : b[s]! > gs[best]!.box[s]!;
      if (better) best = i;
    }
    if (!pick.includes(best)) pick.push(best);
  }
  const c: [number, number, number] = [(box[0] + box[3]) / 2, (box[1] + box[4]) / 2, (box[2] + box[5]) / 2];
  return { box, ids: pick.map((i) => gs[i]!.gid), c, diag: diagOf(box), n: keep.length };
}

const dist3 = (a: readonly number[], b: readonly number[]): number => Math.hypot(a[0]! - b[0]!, a[1]! - b[1]!, a[2]! - b[2]!);

interface Sample {
  t: number;
  /** Elements active in the window ahead, and how much each weighs. */
  win: number[];
  /** Elements active right now. */
  now: number[];
}

interface Shot {
  start: number;
  type: ShotType;
  c: [number, number, number];
  size: number;
}

/**
 * Direct a plan: the cues, in video seconds, that go on top of a `schedule4d` cue of the film; and a line for every decision.
 */
export function directFourD(plan: FourDPlan, model: DirectorModel, opts: DirectorOptions = {}): DirectorResult {
  const style = plan.style;
  const prof = PROFILES[opts.profile ?? 'dynamic'];
  const minShot = opts.minShot ?? prof.minShot;
  const dt = opts.step ?? 0.5;
  const span = mapSpan(plan);
  const dur = opts.duration ?? span;
  const t0 = opts.start ?? 0;
  const out: Array<{ cue: Cue; order: number }> = [];
  const notes: Array<{ t: number; text: string; order: number }> = [];
  let order = 0;
  const empty = (): DirectorResult => ({ cues: [], notes: [], noteTimes: [] });
  if (!(dur > 0) || !(span > 0)) return empty();

  const pt = (tau: number): number => planTimeAt(plan, Math.min(1, Math.max(0, tau / dur)));
  // rounded up to the millisecond: a cue at a hold of the time map must not land before its first second
  const tauOfPlan = (ms: number): number => Math.ceil(((secondsAtPlan(plan, ms) * dur) / span) * 1000 - 1e-6) / 1000;
  const add = (cue: Cue, tau: number, durS: number, extra: Record<string, unknown> = {}): void => {
    out.push({ cue: { ...cue, at: r3(t0 + tau), dur: r3(durS), ...extra } as Cue, order: order++ });
  };
  const note = (tau: number, text: string): void => {
    notes.push({ t: tau, text: `${mmss(t0 + tau)}  ${isoDate(pt(tau))}  ${text}`, order: order++ });
  };

  // ---- the model: geometry per planned element, storeys, footprints
  const byGid = new Map<string, { bbox?: BBox; storey?: string }>();
  for (const e of model.elements) byGid.set(e.globalId, e);
  const modelBox: BBox = [Infinity, Infinity, Infinity, -Infinity, -Infinity, -Infinity];
  const storeyZ = new Map<string, number[]>();
  for (const e of model.elements) {
    if (!e.bbox) continue;
    for (let a = 0; a < 3; a++) {
      modelBox[a] = Math.min(modelBox[a]!, e.bbox[a]!);
      modelBox[a + 3] = Math.max(modelBox[a + 3]!, e.bbox[a + 3]!);
    }
    if (e.storey) {
      if (!storeyZ.has(e.storey)) storeyZ.set(e.storey, []);
      storeyZ.get(e.storey)!.push(e.bbox[2]);
    }
  }
  if (!Number.isFinite(modelBox[0])) {
    notes.push({ t: 0, text: `${mmss(t0)}  ${isoDate(pt(0))}  no element of the model has a bounding box: the director has nothing to frame, no camera moves`, order: order++ });
    return { cues: [], notes: notes.map((n) => n.text), noteTimes: [t0] };
  }
  const modelDiag = diagOf(modelBox);
  const elev = new Map<string, number>();
  for (const s of model.storeys ?? []) elev.set(s.name, s.elevation);
  for (const [name, zs] of storeyZ) {
    if (elev.has(name)) continue;
    zs.sort((a, b) => a - b);
    elev.set(name, zs[Math.floor(zs.length / 2)]!);
  }
  const storeyNames = [...storeyZ.keys()].sort((a, b) => elev.get(a)! - elev.get(b)! || a.localeCompare(b));
  const storeyIndex = new Map(storeyNames.map((n, i) => [n, i]));
  const foot: Array<[number, number, number, number]> = storeyNames.map(() => [Infinity, Infinity, -Infinity, -Infinity]);
  for (const e of model.elements) {
    const si = e.storey ? storeyIndex.get(e.storey) : undefined;
    if (si === undefined || !e.bbox) continue;
    const f = foot[si]!;
    f[0] = Math.min(f[0], e.bbox[0]);
    f[1] = Math.min(f[1], e.bbox[1]);
    f[2] = Math.max(f[2], e.bbox[3]);
    f[3] = Math.max(f[3], e.bbox[4]);
  }

  const gs: G[] = [];
  for (const el of plan.elements) {
    const m = byGid.get(el.globalId);
    if (!m?.bbox) continue;
    const segs: Seg[] = [];
    for (const iv of el.intervals) if (iv.state === 'active' || iv.state === 'behind') segs.push({ from: iv.from, to: iv.to, task: iv.task });
    if (segs.length === 0) continue;
    const b = m.bbox;
    gs.push({ gid: el.globalId, box: b, c: [(b[0] + b[3]) / 2, (b[1] + b[4]) / 2, (b[2] + b[5]) / 2], storey: m.storey !== undefined ? (storeyIndex.get(m.storey) ?? -1) : -1, segs });
  }
  const taskByCode = new Map(plan.tasks.map((t) => [t.code, t]));

  // ---- samples
  const nS = Math.floor(dur / dt + 1e-9) + 1;
  const samples: Sample[] = [];
  const weight = new Array<number>(gs.length).fill(1);
  const winW: number[][] = [];
  for (let i = 0; i < nS; i++) {
    const tau = Math.min(i * dt, dur);
    const pa = pt(tau);
    const pb = pt(Math.min(tau + prof.window, dur));
    const win: number[] = [];
    const now: number[] = [];
    const w: number[] = [];
    for (let k = 0; k < gs.length; k++) {
      let inWin = false;
      let changing = false;
      let inNow = false;
      for (const s of gs[k]!.segs) {
        if (s.from <= pb && s.to > pa) inWin = true;
        if ((s.from > pa && s.from <= pb) || (s.to > pa && s.to <= pb)) changing = true;
        if (s.from <= pa && s.to > pa) inNow = true;
      }
      if (inWin) {
        win.push(k);
        w.push(changing ? 3 : 1);
      }
      if (inNow) now.push(k);
    }
    samples.push({ t: tau, win, now });
    winW.push(w);
  }
  const weightsOf = (i: number): number[] => {
    weight.fill(1);
    const s = samples[i]!;
    s.win.forEach((k, j) => (weight[k] = winW[i]![j]!));
    return weight;
  };

  const directorCamera = style.camera === 'director';
  const blocked: Range[] = [];
  /** Moments after which the camera should look again; `reframe`: even when the shot stays wide (the building changed shape). */
  const kicks: Array<{ t: number; reframe: boolean }> = [];

  // ---- phase milestone beats (explode and orbit around the whole building)
  const beats: Array<{ t: number; name: string }> = [];
  const maxBeats = style.explode === 'auto' ? (opts.maxBeats ?? 3) : 0;
  if (maxBeats > 0 && storeyNames.length >= 2) {
    const ms = [...plan.milestones].sort((a, b) => a.at - b.at || a.code.localeCompare(b.code));
    const inside = ms.filter((m) => m.at > plan.window.from + 0.02 * (plan.window.to - plan.window.from) && tauOfPlan(m.at) + BEAT.end + 0.5 <= dur);
    const phase = inside.filter((m) => PHASE_WORDS.test(m.name));
    const pool = phase.length > 0 ? phase : inside;
    for (const m of pool) {
      if (beats.length >= maxBeats) break;
      const tau = tauOfPlan(m.at);
      if (beats.some((b) => Math.abs(b.t - tau) < BEAT.end + 1)) continue;
      beats.push({ t: tau, name: m.name });
    }
    beats.sort((a, b) => a.t - b.t);
  }
  for (const b of beats) {
    const t = b.t;
    note(t, `beat at "${b.name}": the whole building in focus, explode (${EXPLODE_S} s), ${directorCamera ? 'wide shot, orbit, ' : ''}collapse; the camera waits until it is over (${BEAT.end} s)`);
    add({ kind: 'focus', at: 0, dur: 0, elements: { all: true } }, t, 0);
    add({ kind: 'explode', at: 0, dur: 0, mode: 'storeys', factor: EXPLODE_FACTOR, ease: 'inOut' }, t + BEAT.explode, EXPLODE_S);
    if (directorCamera) {
      add({ kind: 'camera', at: 0, dur: 0, ease: 'inOut', to: { frame: { all: true }, margin: MARGIN.wide } }, t + BEAT.wide, 2);
      add({ kind: 'camera', at: 0, dur: 0, ease: 'linear', to: { orbitDeg: 70 } }, t + BEAT.orbit, BEAT.orbitS);
    }
    add({ kind: 'collapse', at: 0, dur: 0, ease: 'inOut' }, t + BEAT.collapse, COLLAPSE_S);
    add({ kind: 'focus', at: 0, dur: 0, elements: { schedule: 'active' } }, t + BEAT.end, 0);
    blocked.push([t, t + BEAT.end]);
    kicks.push({ t: t + BEAT.end, reframe: true });
  }

  // ---- explode and collapse: work on many storeys at once
  const exploded: Range[] = [];
  const explodeFrom = opts.explodeStoreys ?? 3;
  if (style.explode === 'auto' && storeyNames.length >= 2) {
    const wanted: number[] = [];
    const reasons: string[] = [];
    for (let i = 0; i < samples.length; i++) {
      const win = samples[i]!.win;
      const per = new Array<number>(storeyNames.length).fill(0);
      for (const k of win) if (gs[k]!.storey >= 0) per[gs[k]!.storey]!++;
      const need = Math.max(1, Math.ceil(0.05 * win.length));
      const withWork = per.map((n, s) => (n >= need ? s : -1)).filter((s) => s >= 0);
      let want = false;
      let why = '';
      if (storeyNames.length >= explodeFrom) {
        if (withWork.length >= explodeFrom) {
          want = true;
          why = `work on ${withWork.length} storeys at once`;
        }
      } else if (withWork.length === storeyNames.length && storeyNames.length === 2) {
        // two storeys: both have work and the upper one roofs over the lower work
        const up = foot[1]!;
        const low = win.filter((k) => gs[k]!.storey === 0);
        const under = low.filter((k) => gs[k]!.c[0] >= up[0] && gs[k]!.c[0] <= up[2] && gs[k]!.c[1] >= up[1] && gs[k]!.c[1] <= up[3]);
        if (low.length > 0 && under.length * 2 >= low.length) {
          want = true;
          why = `work on both storeys and the upper one covers the lower work (${under.length} of ${low.length} elements)`;
        }
      }
      if (want) {
        wanted.push(i);
        reasons[i] = why;
      }
    }
    const runs: Range[] = wanted.map((i) => [samples[i]!.t, samples[i]!.t + dt] as Range);
    let merged = mergeRuns(runs, 5);
    merged = merged.map(([a, b]) => [a, Math.min(b, dur - COLLAPSE_S - 0.5)] as Range);
    for (const [a, b] of subtract(merged, blocked)) {
      if (b - a < EXPLODE_S + 4) continue;
      const i0 = Math.round(a / dt);
      add({ kind: 'explode', at: 0, dur: 0, mode: 'storeys', factor: EXPLODE_FACTOR, ease: 'inOut' }, a, EXPLODE_S);
      add({ kind: 'collapse', at: 0, dur: 0, ease: 'inOut' }, b, COLLAPSE_S);
      note(a, `explode storeys: ${reasons[i0] ?? reasons[wanted.find((w) => samples[w]!.t >= a) ?? 0] ?? 'work spread over the storeys'}`);
      note(b, `collapse: the work concentrates again (exploded for ${r3(b - a)} s)`);
      blocked.push([a, a + EXPLODE_S], [b, b + COLLAPSE_S]);
      exploded.push([a + EXPLODE_S, b]);
      kicks.push({ t: a + EXPLODE_S, reframe: true }, { t: b + COLLAPSE_S, reframe: true });
    }
  }
  const explodedAt = (tau: number): boolean => exploded.some(([a, b]) => tau >= a && tau < b + COLLAPSE_S) || beats.some((bt) => tau >= bt.t + BEAT.explode + EXPLODE_S && tau < bt.t + BEAT.collapse + COLLAPSE_S);

  // ---- each floor apart: explode by storey around the floor whose elements are going up
  const floorCaps: Array<{ t: number; title: string; text: string }> = [];
  if (style.explode === 'floor') {
    note(0, 'style explode is "floor": no milestone beats and no work-spread explode; the storeys go apart around the floor being built');
    if (storeyNames.length < 2) note(0, `the model has ${storeyNames.length} storey${storeyNames.length === 1 ? '' : 's'}: nothing to explode apart`);
    else {
      const open = directorCamera ? r3(2.5 * prof.moveScale) + 0.5 : 0;
      const latest = dur - COLLAPSE_S - 0.5;
      // the storey with most of the elements going up at each sample (at least half of those with a storey), -1 when none
      const dom: number[] = samples.map((sm) => {
        const per = new Array<number>(storeyNames.length).fill(0);
        let tot = 0;
        for (const k of sm.now) if (gs[k]!.storey >= 0) { per[gs[k]!.storey]!++; tot++; }
        if (tot === 0) return -1;
        let best = 0;
        for (let i = 1; i < per.length; i++) if (per[i]! > per[best]!) best = i;
        return per[best]! * 2 >= tot ? best : -1;
      });
      // a gap with no work between two samples of one storey belongs to that storey (curing, drying)
      for (let i = 0; i < dom.length; ) {
        if (dom[i] !== -1) { i++; continue; }
        let j = i;
        while (j < dom.length && dom[j] === -1) j++;
        if (i > 0 && j < dom.length && dom[i - 1] === dom[j] && (j - i) * dt <= FLOOR_GAP_S) for (let k = i; k < j; k++) dom[k] = dom[i - 1]!;
        i = j;
      }
      let runs: Array<{ s: number; a: number; b: number }> = [];
      for (let i = 0; i < dom.length; ) {
        if (dom[i]! < 0) { i++; continue; }
        let j = i;
        while (j < dom.length && dom[j] === dom[i]) j++;
        runs.push({ s: dom[i]!, a: samples[i]!.t, b: samples[j - 1]!.t + dt });
        i = j;
      }
      // short blips of another storey inside a run of one storey do not split it
      for (let again = true; again; ) {
        again = false;
        for (let i = 1; i + 1 < runs.length; i++) {
          const p = runs[i - 1]!, m = runs[i]!, n = runs[i + 1]!;
          if (p.s === n.s && p.s !== m.s && m.b - m.a < 2 && n.a - p.b <= FLOOR_GAP_S) {
            runs.splice(i, 2, { s: p.s, a: p.a, b: n.b });
            runs.splice(i - 1, 1);
            again = true;
            break;
          }
        }
      }
      // same storey again soon: the floor stays apart
      const joined: typeof runs = [];
      for (const r of runs) {
        const last = joined[joined.length - 1];
        if (last && last.s === r.s && r.a - last.b <= FLOOR_GAP_S) last.b = r.b;
        else joined.push({ ...r });
      }
      runs = joined;
      const need = EXPLODE_S + FLOOR_HOLD_MIN_S;
      const name = (r: { s: number }): string => storeyNames[r.s]!;
      for (const r of runs) { r.a = Math.max(r.a, open); r.b = Math.min(r.b, latest); }
      // collapse before the work moves on: the next floor starts COLLAPSE_S + FLOOR_REST_S after the last one let go
      const kept: typeof runs = [];
      for (const r of runs) {
        if (r.b - r.a < need) {
          note(r.a, `floor "${name(r)}" has the work for only ${r3(Math.max(0, r.b - r.a))} s: too short for an explode (it needs ${need} s), left as it is`);
          continue;
        }
        const prev = kept[kept.length - 1];
        const gap = COLLAPSE_S + FLOOR_REST_S;
        if (prev && r.a - prev.b < gap) {
          if (prev.b - gap >= prev.a + need && r.a - (prev.b - gap) >= gap) {
            note(prev.b - gap, `floor "${name(prev)}": ends ${r3(gap)} s early so the building can close before the work moves to "${name(r)}"`);
            prev.b = r.a - gap;
          } else if (r.b - (prev.b + gap) >= need) {
            note(r.a, `floor "${name(r)}": explode waits ${r3(prev.b + gap - r.a)} s for the collapse of "${name(prev)}"`);
            r.a = prev.b + gap;
          } else {
            note(r.a, `floor "${name(r)}" left as it is: no room to close "${name(prev)}" first`);
            continue;
          }
        }
        kept.push(r);
      }
      const focusOn = style.xrayFocus;
      kept.forEach((r, i) => {
        const nm = name(r);
        const n = kept[i + 1];
        const going = new Set<number>();
        for (const sm of samples) if (sm.t >= r.a - 1e-9 && sm.t < r.b) for (const k of sm.now) if (gs[k]!.storey === r.s) going.add(k);
        const nIds = going.size;
        add({ kind: 'explode', at: 0, dur: 0, mode: 'storeys', factor: EXPLODE_FACTOR, ease: 'inOut' }, r.a, EXPLODE_S);
        note(r.a, `floor "${nm}": the work moves onto it (${nIds} element${nIds === 1 ? '' : 's'} going up while it is apart): explode the storeys apart (${EXPLODE_S} s), ${focusOn ? 'that floor in x-ray focus, ' : ''}caption with its name, hold ${r3(r.b - r.a - EXPLODE_S)} s`);
        if (focusOn) {
          const ids = model.elements.filter((e) => e.storey === nm).map((e) => e.globalId);
          const ref = !nm.includes('"') && !nm.includes("'") ? { query: `storey = '${nm}'` } : { globalIds: ids };
          add({ kind: 'focus', at: 0, dur: 0, elements: ref }, r.a, 0);
          add({ kind: 'focus', at: 0, dur: 0, elements: { schedule: 'active' } }, r.b + COLLAPSE_S, 0);
        }
        add({ kind: 'collapse', at: 0, dur: 0, ease: 'inOut' }, r.b, COLLAPSE_S);
        note(r.b, n && name(n) === nm ? `collapse (${COLLAPSE_S} s): the work on "${nm}" pauses for ${r3(n.a - r.b)} s (apart for ${r3(r.b - r.a)} s)` : n ? `collapse (${COLLAPSE_S} s) before the work moves on to "${name(n)}" (the floor "${nm}" was apart for ${r3(r.b - r.a)} s)` : `collapse (${COLLAPSE_S} s): the work leaves "${nm}" for good (apart for ${r3(r.b - r.a)} s)`);
        floorCaps.push({ t: r.a + EXPLODE_S * 0.5, title: nm, text: 'Building this floor, the floors held apart' });
        blocked.push([r.a, r.a + EXPLODE_S], [r.b, r.b + COLLAPSE_S]);
        exploded.push([r.a + EXPLODE_S, r.b]);
        kicks.push({ t: r.a + EXPLODE_S, reframe: true }, { t: r.b + COLLAPSE_S, reframe: true });
      });
      if (kept.length === 0) note(0, 'no floor has work for long enough to explode');
    }
  }

  // ---- section box: all work on one storey, inside the envelope
  if (style.sectionBox === 'auto' && storeyNames.length >= 2) {
    const cand: Array<number> = [];
    for (const s of samples) {
      let sole = -2;
      let ok = s.now.length > 0;
      for (const k of s.now) {
        const g = gs[k]!;
        if (g.storey < 0 || (sole !== -2 && g.storey !== sole)) {
          ok = false;
          break;
        }
        sole = g.storey;
        const f = foot[g.storey]!;
        const inset = Math.max(0.3, 0.03 * Math.min(f[2] - f[0], f[3] - f[1]));
        if (!(g.box[0] >= f[0] + inset && g.box[3] <= f[2] - inset && g.box[1] >= f[1] + inset && g.box[4] <= f[3] - inset)) {
          ok = false;
          break;
        }
      }
      cand.push(ok ? sole : -1);
    }
    const need = opts.sectionSeconds ?? 6;
    const runs: Array<{ a: number; b: number; s: number }> = [];
    for (let i = 0; i < cand.length; ) {
      if (cand[i]! < 0) {
        i++;
        continue;
      }
      let j = i;
      let last = i;
      while (j < cand.length && (cand[j] === cand[i] || (cand[j]! < 0 && j - last <= 3))) {
        if (cand[j] === cand[i]) last = j;
        j++;
      }
      runs.push({ a: samples[i]!.t, b: samples[last]!.t + dt, s: cand[i]! });
      i = last + 1;
    }
    const blockers = [...blocked, ...exploded];
    const finals: Array<{ a: number; b: number; s: number }> = [];
    for (const r of runs) for (const [a, b] of subtract([[r.a, r.b]], blockers)) if (b - a >= need) finals.push({ a, b: Math.min(b, dur - 0.5), s: r.s });
    finals.forEach((r, k) => {
      const name = storeyNames[r.s]!;
      add({ kind: 'sectionBox', at: 0, dur: 0, ease: 'inOut', around: { storey: name } }, r.a, SECTION_IN_S);
      note(r.a, `section box around "${name}": all active work is on that storey and inside the envelope for ${r3(r.b - r.a)} s`);
      kicks.push({ t: r.a, reframe: false });
      const next = finals[k + 1];
      if (next && next.a - r.b < 2 && next.s !== r.s) return; // the next box replaces this one
      if (next && next.a - r.b < 2 && next.s === r.s) return;
      // the box opens before an explode or a beat starts, never during it
      const hit = blockers.filter(([b0]) => b0 > r.b - 1e-9 && b0 < r.b + SECTION_OUT_S - 1e-9).map(([b0]) => b0);
      const offAt = hit.length > 0 ? Math.max(r.a, Math.min(...hit) - SECTION_OUT_S) : r.b;
      add({ kind: 'sectionBox', at: 0, dur: 0, ease: 'inOut', around: null }, offAt, SECTION_OUT_S);
      note(offAt, `section box off: the work leaves "${name}"`);
    });
  }

  // ---- the camera
  const camCues: Range[] = [];
  if (directorCamera) {
    const wide: Region = { box: modelBox, ids: [], c: [(modelBox[0] + modelBox[3]) / 2, (modelBox[1] + modelBox[4]) / 2, (modelBox[2] + modelBox[5]) / 2], diag: modelDiag, n: gs.length };
    let cur: Shot = { start: 0, type: 'wide', c: wide.c, size: modelDiag };
    const openDur = r3(2.5 * prof.moveScale);
    add({ kind: 'camera', at: 0, dur: 0, ease: 'inOut', to: { frame: { all: true }, margin: MARGIN.wide } }, 0, openDur);
    camCues.push([0, openDur]);
    note(0, `opening wide shot of the whole model (${r3(openDur)} s)`);
    const appliedBeats = new Set<number>();
    let shots = 0;
    const zoneCams = style.zoneCameras ?? {};
    let curView: string | undefined;
    for (let i = 1; i < samples.length; i++) {
      const tau = samples[i]!.t;
      beats.forEach((b, bi) => {
        if (!appliedBeats.has(bi) && tau >= b.t + BEAT.end) {
          appliedBeats.add(bi);
          cur = { start: b.t + BEAT.orbit, type: 'wide', c: wide.c, size: modelDiag };
          curView = undefined;
          camCues.push([b.t + BEAT.wide, b.t + BEAT.orbit + BEAT.orbitS]);
        }
      });
      if (tau < cur.start + minShot - 1e-9) continue;
      const reg = regionOf(gs, samples[i]!.win, weightsOf(i));
      if (!reg) continue;
      const isExploded = explodedAt(tau);
      const ratio = reg.diag / Math.max(modelDiag, 1e-6);
      let type: ShotType = ratio >= 0.55 ? 'wide' : ratio >= 0.2 ? 'medium' : 'close';
      // hysteresis: stay with the current type near a boundary
      const hold = 0.05;
      if (cur.type !== type && cur.type !== 'wide' && !(isExploded)) {
        const lo = cur.type === 'close' ? 0.2 + hold : 0.2 - hold;
        const hi = cur.type === 'medium' ? 0.55 + hold : 0.55 - hold;
        if (cur.type === 'medium' && ratio >= lo && ratio <= hi) type = 'medium';
        if (cur.type === 'close' && ratio < lo) type = 'close';
      } else if (cur.type === 'wide' && type === 'medium' && ratio > 0.55 - hold) type = 'wide';
      if (isExploded) type = 'wide';
      const want: Shot = type === 'wide' ? { start: tau, type, c: wide.c, size: modelDiag } : { start: tau, type, c: reg.c, size: Math.max(reg.diag, 3) };
      const kick = kicks.some((k) => k.t > cur.start && k.t <= tau && (k.reframe || type !== 'wide'));
      const moved = type !== 'wide' && cur.type !== 'wide' && dist3(want.c, cur.c) > Math.max(cur.size * 0.9, 3);
      const rescaled = type !== 'wide' && cur.type !== 'wide' && (want.size / cur.size > 1.8 || want.size / cur.size < 0.55);
      if (!(kick || type !== cur.type || moved || rescaled)) continue;
      const d = r3(Math.min(3.2 * prof.moveScale, Math.max(2 * prof.moveScale, (1.8 + 0.7 * Math.log2(1 + dist3(want.c, cur.c) / Math.max(want.size, 4))) * prof.moveScale)));
      if (blocked.some(([b0, b1]) => overlaps(tau, tau + d, b0, b1))) continue;
      // a saved view for the storey when all the work in view lies on one storey that has a camera
      let zone: { storey: string; view: string } | undefined;
      if (type !== 'wide') {
        const on = new Set(samples[i]!.win.map((k) => gs[k]!.storey));
        const si = on.size === 1 ? [...on][0]! : -1;
        const view = si >= 0 ? zoneCams[storeyNames[si]!] : undefined;
        if (view) zone = { storey: storeyNames[si]!, view };
      }
      if (zone && curView === zone.view && !kick) continue;
      const frame = type === 'wide' ? { all: true as const } : { globalIds: reg.ids };
      if (zone) add({ kind: 'camera', at: 0, dur: 0, ease: 'inOut', to: { view: zone.view } }, tau, d);
      else add({ kind: 'camera', at: 0, dur: 0, ease: 'inOut', to: { frame, margin: MARGIN[type] } }, tau, d);
      curView = zone?.view;
      camCues.push([tau, tau + d]);
      shots++;
      const names = new Map<string, number>();
      for (const k of samples[i]!.win) for (const s of gs[k]!.segs) if (s.from <= pt(tau + prof.window) && s.to > pt(tau)) names.set(s.task, (names.get(s.task) ?? 0) + 1);
      const top = [...names.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 2).map(([c]) => taskByCode.get(c)?.name ?? c);
      const why = isExploded ? 'the building is exploded' : kick && type === cur.type ? 'new framing after the box or explode change' : type !== cur.type ? `the shot changes from ${cur.type} to ${type}` : 'the work moved by more than the region size';
      if (zone) note(tau, `camera for ${zone.storey}: saved view '${zone.view}' (all the work in view is on that floor, ${type} shot replaced); move ${d} s`);
      else note(tau, `${type} shot on ${reg.n} element${reg.n === 1 ? '' : 's'} (${top.join(', ') || 'work'}): ${why}; move ${d} s`);
      cur = want;
    }
    if (shots === 0) note(0, 'no further camera move: the interest region stays the same');

    // slow orbit in the long gaps
    const occupied: Range[] = [...camCues, ...blocked].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
    let cursor = 0;
    const gaps: Range[] = [];
    for (const [a, b] of occupied) {
      if (a > cursor) gaps.push([cursor, a]);
      cursor = Math.max(cursor, b);
    }
    if (cursor < dur) gaps.push([cursor, dur]);
    for (const [a, b] of gaps) {
      const s = a + 1;
      const d = Math.min(b - 1 - s, 20);
      if (d < 8) continue;
      const deg = Math.round(Math.min(90, d * prof.orbitDegPerS));
      add({ kind: 'camera', at: 0, dur: 0, ease: 'linear', to: { orbitDeg: deg } }, s, d);
      note(s, `slow orbit of ${deg} degrees over ${r3(d)} s: a quiet stretch with no shot change`);
    }
  } else {
    note(0, `no camera moves: the style's camera is "${style.camera}"`);
  }

  // ---- captions at the milestones
  if (style.captions) {
    const first = plan.window.from;
    const title = plan.model.name.replace(/\.(ifc|ifczip|ifcxml)$/i, '') || 'Construction sequence';
    const dates = `${isoDate(plan.window.from)} to ${isoDate(plan.window.to)}`;
    const word = style.view === 'actual' ? 'Actual to date' : style.view === 'variance' ? 'Planned and actual' : 'Planned';
    const caps: Array<{ t: number; title: string; text: string; d: number }> = [{ t: 0, title, text: `${word} ${dates}`, d: 3 }];
    const groups = new Map<number, string[]>();
    for (const m of [...plan.milestones].sort((a, b) => a.at - b.at || a.code.localeCompare(b.code))) {
      if (m.at <= first) continue;
      const k = m.at;
      if (!groups.has(k)) groups.set(k, []);
      groups.get(k)!.push(m.name);
    }
    const skipped = plan.milestones.filter((m) => m.at <= first).map((m) => m.name);
    for (const [at, names] of [...groups.entries()].sort((a, b) => a[0] - b[0])) caps.push({ t: tauOfPlan(at), title: names.join(' / '), text: isoDate(at), d: 3 });
    // a floor caption only where it does not cut a milestone caption short
    for (const f of floorCaps) {
      if (caps.some((c) => Math.abs(c.t - f.t) < 1.5)) {
        note(f.t, `caption "${f.title}" left out: a milestone caption is too close`);
        continue;
      }
      caps.push({ t: f.t, title: f.title, text: f.text, d: FLOOR_CAPTION_S });
    }
    // temporary works are context, never framed: a scaffold that goes up is named in one line, merged into a caption that is near anyway
    for (const g of plan.temporaryWorks?.groups ?? []) {
      if (g.kind !== 'scaffold' || g.erect.to < plan.window.from || g.erect.to > plan.window.to) continue;
      const t = tauOfPlan(g.erect.to);
      const line = `Scaffold up${g.storey !== undefined ? ` on ${g.storey}` : ''}`;
      const near = caps.find((c) => Math.abs(c.t - t) < 2.5);
      if (near) {
        if (near.text.length + line.length < 70) { near.text = `${near.text} · ${line}`; note(near.t, `caption "${near.title}" also says "${line}" (scaffold erected)`); }
      } else if (!caps.some((c) => Math.abs(c.t - t) < 4)) caps.push({ t, title: line, text: isoDate(g.erect.to), d: 2.5 });
    }
    caps.sort((a, b) => a.t - b.t);
    caps.forEach((c, i) => {
      const nextT = caps[i + 1]?.t ?? Infinity;
      const d = Math.min(c.d, nextT - c.t - 0.3, dur - c.t);
      if (d < 1.2) {
        note(c.t, `caption "${c.title}" left out: the next caption is too close`);
        return;
      }
      add({ kind: 'caption', at: 0, dur: 0, title: c.title, text: c.text }, c.t, r3(d));
      note(c.t, floorCaps.some((f) => f.t === c.t && f.title === c.title) ? `floor caption "${c.title}"` : i === 0 ? `title caption "${c.title}"${skipped.length ? ` (the start milestones ${skipped.map((s) => `"${s}"`).join(', ')} are folded into it)` : ''}` : `milestone caption "${c.title}"`);
    });
  }

  // ---- labels on the largest active activities
  const maxLabels = opts.labels ?? style.labels;
  if (maxLabels > 0) {
    const top: string[][] = samples.map((s) => {
      const by = new Map<string, number>();
      for (const k of s.now) for (const sg of gs[k]!.segs) if (sg.from <= pt(s.t) && sg.to > pt(s.t)) by.set(sg.task, (by.get(sg.task) ?? 0) + 1);
      return [...by.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, maxLabels).map(([c]) => c);
    });
    const open = new Map<string, number>();
    const finish = (code: string, from: number, to: number): void => {
      if (to - from < LABEL_MIN_S) return;
      const d = Math.min(to - from, LABEL_MAX_S);
      // the element of the activity nearest to the centre of its active elements
      const members: number[] = [];
      const pa = pt(from);
      for (const k of samples[Math.round(from / dt)]!.now) if (gs[k]!.segs.some((sg) => sg.task === code && sg.from <= pa && sg.to > pa)) members.push(k);
      if (members.length === 0) return;
      const cx = members.reduce((n, k) => n + gs[k]!.c[0], 0) / members.length;
      const cy = members.reduce((n, k) => n + gs[k]!.c[1], 0) / members.length;
      const cz = members.reduce((n, k) => n + gs[k]!.c[2], 0) / members.length;
      let best = members[0]!;
      for (const k of members) if (dist3(gs[k]!.c, [cx, cy, cz]) < dist3(gs[best]!.c, [cx, cy, cz]) - 1e-9) best = k;
      add({ kind: 'label', at: 0, dur: 0, elements: { globalIds: [gs[best]!.gid] }, fields: [...LABEL_FIELDS] }, from, r3(d));
      const t = taskByCode.get(code);
      note(from, `label "${t?.name ?? code}" (${code}, ${members.length} active element${members.length === 1 ? '' : 's'}) for ${r3(d)} s: among the ${maxLabels} largest active activities`);
    };
    for (let i = 0; i < samples.length; i++) {
      const now = new Set(top[i]);
      for (const [code, from] of [...open]) {
        if (!now.has(code)) {
          open.delete(code);
          finish(code, from, samples[i]!.t);
        }
      }
      for (const code of now) if (!open.has(code)) open.set(code, samples[i]!.t);
    }
    for (const [code, from] of open) finish(code, from, dur);
  }

  // ---- finale: a closing dolly and/or orbit after the last work
  let filmEnd: number | undefined;
  const finale = style.finale ?? 'none';
  if (finale !== 'none') {
    if (!directorCamera) note(dur, `finale "${finale}" left out: the style's camera is "${style.camera}", the director moves no camera`);
    else {
      let f0 = dur;
      const apart = exploded.filter(([, b]) => b >= dur - 0.01).length > 0 || beats.some((b) => b.t + BEAT.collapse + COLLAPSE_S > dur);
      if (apart) {
        add({ kind: 'collapse', at: 0, dur: 0, ease: 'inOut' }, f0, COLLAPSE_S);
        note(f0, `finale: the building is still apart, collapse (${COLLAPSE_S} s) first`);
        f0 += COLLAPSE_S;
      }
      // the film's own x-ray focus follows the active work and ends with it; a focus cue is needed only where the director set one
      const focusSet = exploded.length > 0 || beats.length > 0;
      if (focusSet) add({ kind: 'focus', at: 0, dur: 0, elements: null }, f0, 0);
      let lastCam = 0;
      for (const o of out) if (o.cue.kind === 'camera') lastCam = Math.max(lastCam, o.cue.at - t0 + o.cue.dur);
      let t = Math.max(f0, lastCam);
      const last = [...plan.milestones].sort((a, b) => a.at - b.at)[plan.milestones.length - 1];
      const title = last?.name ?? 'Complete';
      note(f0, `finale "${finale}": the work is complete, ${focusSet ? "focus cleared" : "no focus left to clear"}${t > f0 ? `, the camera is free after ${r3(t - f0)} s` : ''}`);
      if (finale === 'dolly') {
        add({ kind: 'camera', at: 0, dur: 0, ease: 'inOut', to: { frame: { all: true }, margin: DOLLY_MARGIN } }, t, DOLLY_S);
        note(t, `finale: slow dolly-in toward the finished building (${DOLLY_S} s, eased in and out)`);
        t += DOLLY_S;
      }
      add({ kind: 'camera', at: 0, dur: 0, ease: 'inOut', to: { orbitDeg: FINALE_ORBIT_DEG } }, t, FINALE_ORBIT_S);
      if (style.captions) add({ kind: 'caption', at: 0, dur: 0, title, text: isoDate(plan.window.to) }, t, FINALE_ORBIT_S);
      note(t, `finale: gentle ${FINALE_ORBIT_DEG} degree orbit over ${FINALE_ORBIT_S} s, eased in and out${style.captions ? `, caption "${title}"` : ''}`);
      filmEnd = t0 + t + FINALE_ORBIT_S;
    }
  }

  // ---- result: cues by time (the order of making breaks ties), notes by time
  out.sort((a, b) => a.cue.at - b.cue.at || a.order - b.order);
  notes.sort((a, b) => a.t - b.t || a.order - b.order);
  return { cues: out.map((o) => o.cue), notes: notes.map((n) => n.text), noteTimes: notes.map((n) => r3(t0 + n.t)), ...(filmEnd !== undefined ? { duration: r3(filmEnd) } : {}) };
}
