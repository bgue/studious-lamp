// The 4D camera director: its rules on synthetic buildings, on the FZK-Haus sample plan, and the script it writes (round trip).
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { directFourD } from '../src/schedule/director';
import type { DirectorResult } from '../src/schedule/director';
import { scriptFromPlan } from '../src/schedule/directorScript';
import { compileScript } from '../src/anim/script/compiler';
import type { Cue } from '../src/anim/score';
import { parseXer } from '../src/schedule/xer';
import { fromSidecar } from '../src/schedule/model';
import { linkSchedule } from '../src/schedule/link';
import { buildPlan } from '../src/schedule/plan';
import type { FourDConfig, FourDPlan } from '../src/schedule/types';
import { el, synth } from './director-helpers';
import type { Work } from './director-helpers';

type CamCue = Extract<Cue, { kind: 'camera' }>;
const of = <K extends Cue['kind']>(r: DirectorResult, kind: K): Array<Extract<Cue, { kind: K }>> => r.cues.filter((c) => c.kind === kind) as Array<Extract<Cue, { kind: K }>>;
const isOrbit = (c: CamCue): boolean => 'orbitDeg' in c.to;
/** Elements 4..7 (the inner ones) of storey `s`, active from..to. */
const inner = (s: number, from: number, to: number, task: string): Work[] => [4, 5, 6, 7].map((k) => ({ el: el(s, k), from, to, task }));

const overlap = (a: [number, number], b: [number, number]): boolean => a[0] < b[1] - 1e-9 && a[1] > b[0] + 1e-9;
const span = (c: Cue): [number, number] => [c.at, c.at + c.dur];

/** Work that wanders over a 4-storey building for 90 s. */
function wander(): Work[] {
  return [
    ...inner(0, 0, 14, 'A'),
    ...[0, 1, 2, 3].map((k) => ({ el: el(1, k), from: 10, to: 30, task: 'B' })),
    ...inner(2, 28, 50, 'C'),
    ...inner(3, 48, 70, 'D'),
    ...inner(1, 66, 88, 'E'),
  ];
}

describe('director: camera', () => {
  const s = synth({ storeys: 4, seconds: 90, work: wander() });
  const r = directFourD(s.plan, s.model);
  const cams = of(r, 'camera');

  it('moves the camera with frame cues and an orbit, each shot at least 4 s', () => {
    const moves = cams.filter((c) => !isOrbit(c));
    expect(moves.length).toBeGreaterThanOrEqual(3);
    for (const c of moves) expect('frame' in c.to).toBe(true);
    for (let i = 1; i < moves.length; i++) expect(moves[i]!.at - moves[i - 1]!.at).toBeGreaterThanOrEqual(4 - 1e-6);
    // no two camera cues of any kind start within 3 s
    for (let i = 1; i < cams.length; i++) expect(cams[i]!.at - cams[i - 1]!.at).toBeGreaterThanOrEqual(3 - 1e-6);
  });

  it('frames the active elements by GlobalId, and the whole model when wide', () => {
    const frames = cams.map((c) => ('frame' in c.to ? c.to.frame : null)).filter(Boolean) as Array<Record<string, unknown>>;
    expect(frames.some((f) => 'all' in f)).toBe(true);
    expect(frames.some((f) => 'globalIds' in f && (f.globalIds as string[]).every((g) => s.gids.includes(g)))).toBe(true);
  });

  it('the opening shot is wide, at the start', () => {
    expect(cams[0]!.at).toBe(0);
    expect((cams[0]!.to as { frame: object }).frame).toEqual({ all: true });
  });

  it('is deterministic', () => {
    expect(JSON.stringify(directFourD(s.plan, s.model))).toBe(JSON.stringify(r));
    // also through a JSON round trip of the plan, as the CLI reads it
    expect(JSON.stringify(directFourD(JSON.parse(JSON.stringify(s.plan)) as FourDPlan, s.model))).toBe(JSON.stringify(r));
  });

  it('style camera fixed or none: no camera cues at all', () => {
    for (const camera of ['fixed', 'none'] as const) {
      const x = directFourD({ ...s.plan, style: { ...s.plan.style, camera } }, s.model);
      expect(of(x, 'camera')).toEqual([]);
      expect(x.notes.join('\n')).toMatch(/no camera moves/);
    }
  });

  it('a slow orbit fills a long quiet stretch, and a calm profile makes longer shots', () => {
    const q = synth({ storeys: 3, seconds: 60, work: inner(1, 0, 60, 'Q') });
    const x = directFourD(q.plan, q.model);
    const orbits = of(x, 'camera').filter(isOrbit);
    expect(orbits.length).toBeGreaterThanOrEqual(1);
    for (const o of orbits) {
      expect(o.dur).toBeGreaterThanOrEqual(8);
      expect(Math.abs((o.to as { orbitDeg: number }).orbitDeg)).toBeLessThanOrEqual(90);
    }
    const calm = of(directFourD(s.plan, s.model, { profile: 'calm' }), 'camera').filter((c) => !isOrbit(c));
    for (let i = 1; i < calm.length; i++) expect(calm[i]!.at - calm[i - 1]!.at).toBeGreaterThanOrEqual(6 - 1e-6);
  });
});

describe('director: explode and collapse', () => {
  // four storeys all have work from 10 to 30 s: explode, then collapse
  const work: Work[] = [0, 1, 2, 3].flatMap((st) => inner(st, 10, 30, `T${st}`));
  const s = synth({ storeys: 4, seconds: 60, work });
  const r = directFourD(s.plan, s.model);

  it('explodes when work is on 3 or more storeys at once and collapses after', () => {
    const ex = of(r, 'explode');
    const co = of(r, 'collapse');
    expect(ex).toHaveLength(1);
    expect(co).toHaveLength(1);
    expect(ex[0]!.mode).toBe('storeys');
    expect(ex[0]!.at).toBeGreaterThanOrEqual(5);
    expect(ex[0]!.at).toBeLessThanOrEqual(11);
    expect(co[0]!.at).toBeGreaterThan(ex[0]!.at + ex[0]!.dur + 4 - 1e-6);
    expect(co[0]!.at).toBeLessThanOrEqual(31);
    expect(r.notes.some((n) => /explode storeys: work on 4 storeys/.test(n))).toBe(true);
  });

  it('never moves the camera while exploding or collapsing', () => {
    const blocks = [...of(r, 'explode'), ...of(r, 'collapse')].map(span);
    for (const c of of(r, 'camera')) for (const b of blocks) expect(overlap(span(c), b), `${c.at} vs ${b}`).toBe(false);
    // and the camera reframes (wide) after the explode
    expect(of(r, 'camera').some((c) => c.at >= of(r, 'explode')[0]!.at + 2 && c.at <= of(r, 'collapse')[0]!.at && 'frame' in c.to && 'all' in c.to.frame)).toBe(true);
  });

  it('does not explode when the work stays on one or two storeys', () => {
    const two = synth({ storeys: 4, seconds: 60, work: [...inner(0, 5, 40, 'A'), ...inner(2, 5, 40, 'B')] });
    expect(of(directFourD(two.plan, two.model), 'explode')).toEqual([]);
  });

  it('style explode off: no explode, collapse or beats', () => {
    const x = directFourD({ ...s.plan, style: { ...s.plan.style, explode: 'off' }, milestones: [{ code: 'M', name: 'Frame complete', at: s.plan.window.from + 20 * 86400000 }] }, s.model);
    expect([...of(x, 'explode'), ...of(x, 'collapse'), ...of(x, 'focus')]).toEqual([]);
  });

  it('a two-storey model explodes when both storeys have work and the upper one covers the lower work', () => {
    const w = synth({ storeys: 2, seconds: 40, work: [...inner(0, 8, 30, 'L'), ...inner(1, 8, 30, 'U')] });
    const x = directFourD(w.plan, w.model);
    expect(of(x, 'explode')).toHaveLength(1);
    expect(x.notes.join('\n')).toMatch(/upper one covers the lower work/);
    // work on one storey only: no explode
    const one = synth({ storeys: 2, seconds: 40, work: inner(1, 8, 30, 'U') });
    expect(of(directFourD(one.plan, one.model), 'explode')).toEqual([]);
  });

  it('a phase milestone gets an explode-and-orbit beat with a whole-building focus, and the camera waits for it', () => {
    const b = synth({ storeys: 3, seconds: 60, work: [...inner(0, 0, 20, 'A'), ...inner(1, 20, 40, 'B')], milestones: [{ name: 'Frame complete', at: 25 }] });
    const x = directFourD(b.plan, b.model);
    const ex = of(x, 'explode');
    expect(ex).toHaveLength(1);
    expect(ex[0]!.at).toBeCloseTo(25, 2);
    const focus = of(x, 'focus');
    expect(focus.map((f) => f.elements)).toEqual([{ all: true }, { schedule: 'active' }]);
    expect(of(x, 'collapse')).toHaveLength(1);
    const beat: [number, number] = [25, 25 + 11.6];
    const inside = of(x, 'camera').filter((c) => overlap(span(c), beat));
    expect(inside.length).toBe(2); // the beat's own wide shot and orbit
    expect(inside.every((c) => c.at >= 25 + 2 - 1e-6)).toBe(true);
    expect(of(x, 'camera').some((c) => c.at < 25 && c.at + c.dur > 25)).toBe(false);
  });
});

describe('director: section box', () => {
  // all work on level 2 (inside the walls) for 24 s, then on level 3
  const s = synth({ storeys: 3, seconds: 60, work: [...inner(1, 8, 32, 'IN'), ...inner(2, 36, 56, 'UP')] });
  const r = directFourD(s.plan, s.model);

  it('boxes the storey when all active work is on it, inside the envelope, for 6 s or more, and opens it when the work leaves', () => {
    const boxes = of(r, 'sectionBox');
    const on = boxes.filter((b) => b.around !== null);
    expect(on.length).toBeGreaterThanOrEqual(2);
    expect(on[0]!.around).toEqual({ storey: 'Level 2' });
    expect(on[0]!.at).toBeGreaterThanOrEqual(3);
    expect(on[0]!.at).toBeLessThanOrEqual(9);
    const off = boxes.find((b) => b.around === null && b.at > on[0]!.at)!;
    expect(off.at).toBeGreaterThanOrEqual(30);
    expect(off.at).toBeLessThanOrEqual(34);
    expect(on[1]!.around).toEqual({ storey: 'Level 3' });
  });

  it('no box for work on the envelope (the walls), on several storeys, or for less than 6 s', () => {
    const walls = synth({ storeys: 3, seconds: 40, work: [0, 1, 2, 3].map((k) => ({ el: el(1, k), from: 5, to: 30, task: 'W' })) });
    expect(of(directFourD(walls.plan, walls.model), 'sectionBox')).toEqual([]);
    const two = synth({ storeys: 3, seconds: 40, work: [...inner(0, 5, 30, 'A'), ...inner(1, 5, 30, 'B')] });
    expect(of(directFourD(two.plan, two.model), 'sectionBox')).toEqual([]);
    const short = synth({ storeys: 3, seconds: 40, work: inner(1, 10, 13, 'S') });
    expect(of(directFourD(short.plan, short.model), 'sectionBox')).toEqual([]);
  });

  it('style sectionBox off: none', () => {
    expect(of(directFourD({ ...s.plan, style: { ...s.plan.style, sectionBox: 'off' } }, s.model), 'sectionBox')).toEqual([]);
  });

  it('never has a box and an explode at once', () => {
    const w: Work[] = [...inner(1, 0, 20, 'IN'), ...[0, 1, 2, 3].flatMap((st) => inner(st, 24, 44, `T${st}`))];
    const m = synth({ storeys: 4, seconds: 60, work: w });
    const x = directFourD(m.plan, m.model);
    const exploded: Array<[number, number]> = of(x, 'explode').map((e, i) => [e.at, of(x, 'collapse')[i]!.at + 2]);
    expect(exploded.length).toBe(1);
    const boxes = of(x, 'sectionBox');
    for (const b of boxes) for (const e of exploded) expect(overlap([b.at, b.at + b.dur], e)).toBe(false);
  });
});

describe('director: captions, labels and focus', () => {
  const ms = [{ name: 'Frame complete', at: 20 }, { name: 'Envelope closed', at: 40 }];
  const work: Work[] = [0, 1, 2, 3, 4].flatMap((t) => [{ el: el(0, 4 + (t % 4)), from: t * 2, to: 50, task: `T${t}` }, { el: el(1, 4 + (t % 4)), from: t * 2 + 1, to: 50, task: `T${t}` }]);
  const s = synth({ storeys: 2, seconds: 60, work, milestones: ms, style: { labels: 2 } });
  const r = directFourD(s.plan, s.model);

  it('captions the milestones and the title', () => {
    const caps = of(r, 'caption');
    expect(caps.map((c) => c.title)).toEqual(['synth', 'Frame complete', 'Envelope closed']);
    expect(caps[1]!.at).toBeCloseTo(20, 2);
    for (let i = 1; i < caps.length; i++) expect(caps[i]!.at).toBeGreaterThanOrEqual(caps[i - 1]!.at + caps[i - 1]!.dur - 1e-6);
    expect(of(directFourD({ ...s.plan, style: { ...s.plan.style, captions: false } }, s.model), 'caption')).toEqual([]);
  });

  it('merges milestones that fall on one moment into one caption', () => {
    const x = directFourD({ ...s.plan, milestones: [...s.plan.milestones, { code: 'M9', name: 'Handover', at: s.plan.milestones[1]!.at }] }, s.model);
    expect(of(x, 'caption').map((c) => c.title)).toContain('Envelope closed / Handover');
  });

  it('at most style.labels labels at a time, each 3 s or longer, on one representative element', () => {
    const labels = of(r, 'label');
    expect(labels.length).toBeGreaterThan(0);
    for (const l of labels) {
      expect(l.dur).toBeGreaterThanOrEqual(3);
      expect(l.dur).toBeLessThanOrEqual(8);
      expect('globalIds' in l.elements && l.elements.globalIds.length === 1).toBe(true);
      expect(l.fields).toEqual(['activity', 'percent', 'finish']);
    }
    for (let t = 0; t < 60; t += 0.25) expect(labels.filter((l) => l.at <= t && t < l.at + l.dur).length).toBeLessThanOrEqual(2);
    expect(of(directFourD({ ...s.plan, style: { ...s.plan.style, labels: 0 } }, s.model), 'label')).toEqual([]);
    expect(of(directFourD(s.plan, s.model, { labels: 1 }), 'label').length).toBeGreaterThan(0);
  });

  it('leaves the x-ray focus to the schedule runner: no focus cues without a beat', () => {
    expect(of(directFourD({ ...s.plan, milestones: [] }, s.model), 'focus')).toEqual([]);
    expect(of(r, 'focus').length).toBe(4); // two beats, each a whole-building focus and the active work back
  });

  it('explains every decision with a time and a date', () => {
    expect(r.notes.length).toBeGreaterThan(5);
    for (const n of r.notes) expect(n).toMatch(/^\d\d:\d\d\.\d {2}\d{4}-\d\d-\d\d {2}\S/);
    expect(r.noteTimes).toHaveLength(r.notes.length);
  });

  it('gives nothing for an empty plan and for a model without boxes', () => {
    const e = synth({ storeys: 2, seconds: 20, work: [] });
    expect(of(directFourD(e.plan, e.model), 'explode')).toEqual([]);
    const nb = directFourD(e.plan, { elements: e.model.elements.map((x) => ({ globalId: x.globalId })) });
    expect(nb.cues).toEqual([]);
    expect(nb.notes[0]).toMatch(/no element of the model has a bounding box/);
  });
});

// ---------------------------------------------------------------- the FZK-Haus sample

const file = (p: string): string => fileURLToPath(new URL(p, import.meta.url));
const schedule = parseXer(readFileSync(file('../public/samples/fzk-haus.xer')));
const config = JSON.parse(readFileSync(file('../public/samples/fzk-haus.4d.json'), 'utf8')) as FourDConfig;
const fzkModel = fromSidecar(JSON.parse(readFileSync(file('../public/models/fzk-haus.json'), 'utf8')), { identityKey: 'fzk-sample' });
const fzkLinks = linkSchedule(schedule, fzkModel, config, []);
/** The sample as the sample ships it (each floor apart), and with the work-spread explode and the milestone beats. */
const fzkFloorPlan = buildPlan(schedule, fzkLinks, fzkModel, config.style);
const fzkPlan = buildPlan(schedule, fzkLinks, fzkModel, { ...config.style, explode: 'auto' });

describe('director on the FZK-Haus sample', () => {
  const r = directFourD(fzkPlan, fzkModel);
  const t = (ms: number): number => {
    const m = fzkPlan.timeMap;
    for (let i = 1; i < m.length; i++) if (m[i]![0] >= ms) return m[i - 1]![0] === m[i]![0] ? m[i - 1]![1] : m[i - 1]![1] + ((ms - m[i - 1]![0]) / (m[i]![0] - m[i - 1]![0])) * (m[i]![1] - m[i - 1]![1]);
    return m[m.length - 1]![1];
  };

  it('captions the milestones at their holds', () => {
    const caps = of(r, 'caption');
    for (const m of fzkPlan.milestones.filter((x) => x.at > fzkPlan.window.from)) {
      const c = caps.find((x) => x.title!.includes(m.name))!;
      expect(c, m.name).toBeDefined();
      expect(c.at).toBeCloseTo(t(m.at), 1);
    }
  });

  it('explodes around the roof carpentry: the topping-out beat, with the camera out of the way', () => {
    const top = fzkPlan.milestones.find((m) => m.name.startsWith('Topping-out'))!;
    const ex = of(r, 'explode');
    expect(ex.length).toBeGreaterThanOrEqual(1);
    expect(ex.some((e) => Math.abs(e.at - t(top.at)) < 0.5)).toBe(true);
    const rafters = fzkPlan.tasks.find((x) => x.name === 'Rafters')!;
    expect(Math.abs(ex[0]!.at - t(rafters.end))).toBeLessThan(3);
    const blocks = [...ex, ...of(r, 'collapse')].map(span);
    for (const c of of(r, 'camera')) for (const b of blocks) expect(overlap(span(c), b)).toBe(false);
    expect(r.notes.some((n) => /beat at "Topping-out/.test(n))).toBe(true);
  });

  it('boxes the attic while the first-floor slab and gable walls are built, and labels the larger activities', () => {
    expect(of(r, 'sectionBox').some((b) => b.around !== null && 'storey' in b.around && b.around.storey === 'Dachgeschoss')).toBe(true);
    expect(of(r, 'label').length).toBeGreaterThan(3);
  });

  it('is deterministic and fits the film', () => {
    expect(JSON.stringify(directFourD(fzkPlan, fzkModel))).toBe(JSON.stringify(r));
    for (const c of r.cues) expect(c.at + c.dur).toBeLessThanOrEqual(90 + 1e-6);
  });
});

// ---------------------------------------------------------------- the script

/** JSON with sorted keys. */
const canon = (v: unknown): string => JSON.stringify(v, (_k, x) => (x && typeof x === 'object' && !Array.isArray(x) ? Object.fromEntries(Object.entries(x as object).sort(([a], [b]) => (a < b ? -1 : 1))) : x));

type Norm = { kind: string; at: number; dur: number; rest: string };
/** Cues without the schedule cue and the script lines, sorted by what they do and then when. */
function normalise(cues: readonly Cue[]): Norm[] {
  return cues
    .filter((c) => c.kind !== 'schedule4d')
    .map((c) => {
      const { at, dur, line: _line, ...rest } = c as Cue & { line?: number };
      return { kind: c.kind, at, dur, rest: canon(rest) };
    })
    .sort((a, b) => (a.rest < b.rest ? -1 : a.rest > b.rest ? 1 : a.at - b.at));
}

function roundTrip(plan: FourDPlan, res: DirectorResult): { text: string; compiled: Cue[] } {
  const text = scriptFromPlan(plan, res, { planName: 'Plan' });
  const c = compileScript(text, { plans: (n) => (n === 'Plan' ? plan : null) });
  expect(c.errors.filter((e) => e.severity === 'error')).toEqual([]);
  return { text, compiled: c.score!.cues };
}

function expectEquivalent(directed: readonly Cue[], compiled: readonly Cue[]): void {
  const a = normalise(directed);
  const b = normalise(compiled);
  expect(b.length).toBe(a.length);
  a.forEach((x, i) => {
    expect(b[i]!.kind).toBe(x.kind);
    expect(b[i]!.rest).toBe(x.rest);
    expect(Math.abs(b[i]!.at - x.at), `${x.kind} ${x.rest}`).toBeLessThan(0.02);
    expect(Math.abs(b[i]!.dur - x.dur)).toBeLessThan(0.002);
  });
}

describe('scriptFromPlan', () => {
  it('round-trips the synthetic films: compiling the script gives the director\'s cues', () => {
    const b = synth({ storeys: 4, seconds: 90, work: wander(), milestones: [{ name: 'Frame complete', at: 40 }, { name: 'Closed', at: 75 }], style: { labels: 2 } });
    const res = directFourD(b.plan, b.model);
    expect(res.cues.length).toBeGreaterThan(15);
    const { compiled } = roundTrip(b.plan, res);
    expectEquivalent(res.cues, compiled);
  });

  it('round-trips the FZK film, with holds at the milestones', () => {
    const res = directFourD(fzkPlan, fzkModel);
    const { text, compiled } = roundTrip(fzkPlan, res);
    expectEquivalent(res.cues, compiled);
    expect(text).toMatch(/^-- generated by xray-4d/);
    expect(text).toMatch(/^schedule "Plan" view planned from "2027-03-01" to "2027-08-04" over 90 seconds$/m);
    expect(text).toMatch(/^at milestone "Building weathertight"$/m);
    expect(text).toMatch(/^at date "2027-/m);
    expect(text).toMatch(/^-- 00:41\.\d {2}2027-05-21 {2}beat at "Topping-out/m);
    expect(text).toMatch(/section box around storey "Dachgeschoss" over 1\.5 seconds/);
  });

  it('puts the cues of one moment into a together block, and can leave the notes out', () => {
    const res = directFourD(fzkPlan, fzkModel);
    const text = scriptFromPlan(fzkPlan, res, { planName: 'Plan', notes: false });
    expect(text).not.toMatch(/beat at/);
    expect(text).toMatch(/^together\n {2}fly to everything over 2\.5 seconds margin 1\.3\n {2}caption "AC20-FZK-Haus"/m);
  });

  it('says what the language cannot say as a comment instead of dropping it silently', () => {
    const res: DirectorResult = { cues: [{ kind: 'param', at: 1, dur: 0, path: 'a.b', to: 1 }, { kind: 'caption', at: 2, dur: 1, title: 'x "y"' }], notes: [], noteTimes: [] };
    const text = scriptFromPlan(fzkPlan, res, { planName: 'Plan' });
    expect(text).toMatch(/-- \(a param cue at 1 s that the script language cannot say was left out\)/);
    expect(text).toContain('caption "x ""y""" for 1 seconds');
  });
});
