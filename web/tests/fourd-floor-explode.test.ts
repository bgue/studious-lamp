// The director's "each floor apart" (style.explode 'floor'): on a small two-storey plan and on the FZK-Haus sample; the style fields in the .4d.json.
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
import { DEFAULT_STYLE } from '../src/schedule/types';
import type { FourDConfig } from '../src/schedule/types';
import { emptyConfig, parseConfig, serializeConfig, setStyle } from '../src/map4d/scheduleConfig';
import { el, synth } from './director-helpers';
import type { Work } from './director-helpers';

const of = <K extends Cue['kind']>(r: DirectorResult, kind: K): Array<Extract<Cue, { kind: K }>> => r.cues.filter((c) => c.kind === kind) as Array<Extract<Cue, { kind: K }>>;
const span = (c: Cue): [number, number] => [c.at, c.at + c.dur];
const overlap = (a: [number, number], b: [number, number]): boolean => a[0] < b[1] - 1e-9 && a[1] > b[0] + 1e-9;
const inner = (s: number, from: number, to: number, task: string): Work[] => [4, 5, 6, 7].map((k) => ({ el: el(s, k), from, to, task }));

/** Level 1 is built from 4 to 30 s, Level 2 from 36 to 70 s; the film lasts 80 s. */
const work = (): Work[] => [...inner(0, 4, 30, 'A'), ...inner(1, 36, 70, 'B')];

describe('director: each floor apart', () => {
  const s = synth({ storeys: 2, seconds: 80, work: work(), style: { explode: 'floor' }, milestones: [{ name: 'Frame complete', at: 33 }] });
  const r = directFourD(s.plan, s.model);
  const ex = of(r, 'explode');
  const co = of(r, 'collapse');

  it('explodes by storeys once per floor and collapses before the work moves on', () => {
    expect(ex.map((c) => c.mode)).toEqual(['storeys', 'storeys']);
    expect(co.length).toBe(2);
    // order: explode, collapse, explode, collapse
    const seq = r.cues.filter((c) => c.kind === 'explode' || c.kind === 'collapse').map((c) => c.kind);
    expect(seq).toEqual(['explode', 'collapse', 'explode', 'collapse']);
    // the first floor goes apart as its work starts (after the opening move) and the second one follows the first collapse
    expect(ex[0]!.at).toBeGreaterThanOrEqual(3);
    expect(ex[0]!.at).toBeLessThan(8);
    expect(co[0]!.at).toBeGreaterThan(ex[0]!.at + ex[0]!.dur + 3);
    expect(ex[1]!.at).toBeGreaterThanOrEqual(co[0]!.at + co[0]!.dur + 1 - 1e-6);
    expect(ex[1]!.at).toBeLessThan(40);
    expect(co[1]!.at).toBeGreaterThan(ex[1]!.at + 4);
    expect(co[1]!.at + co[1]!.dur).toBeLessThanOrEqual(80);
  });

  it('puts the active floor in x-ray focus while apart and gives the focus back to the work after the collapse', () => {
    const focus = of(r, 'focus');
    const query = focus.filter((f) => f.elements !== null && 'query' in f.elements);
    expect(query.map((f) => (f.elements as { query: string }).query)).toEqual(["storey = 'Level 1'", "storey = 'Level 2'"]);
    expect(query[0]!.at).toBeCloseTo(ex[0]!.at, 3);
    const back = focus.filter((f) => f.elements !== null && 'schedule' in f.elements);
    expect(back.length).toBe(2);
    expect(back[0]!.at).toBeCloseTo(co[0]!.at + co[0]!.dur, 3);
  });

  it('names the floor in a caption', () => {
    const caps = of(r, 'caption').map((c) => c.title);
    expect(caps).toContain('Level 1');
    expect(caps).toContain('Level 2');
  });

  it('keeps the camera still during explode and collapse and moves at least 3 s apart', () => {
    const blocks = [...ex, ...co].map(span);
    const cams = of(r, 'camera');
    for (const c of cams) for (const b of blocks) expect(overlap(span(c), b), `camera ${c.at} vs ${b}`).toBe(false);
    for (let i = 1; i < cams.length; i++) expect(cams[i]!.at - cams[i - 1]!.at).toBeGreaterThanOrEqual(3 - 1e-6);
    // no milestone beat and no section box while apart
    expect(r.notes.some((n) => /beat at/.test(n))).toBe(false);
    for (const b of of(r, 'sectionBox')) for (const x of blocks) expect(overlap(span(b), x)).toBe(false);
  });

  it('writes every decision into the notes', () => {
    const text = r.notes.join('\n');
    expect(text).toMatch(/style explode is "floor"/);
    expect(text).toMatch(/floor "Level 1": the work moves onto it .*explode the storeys apart \(2 s\), that floor in x-ray focus, caption with its name/);
    expect(text).toMatch(/collapse \(2 s\) before the work moves on to "Level 2"/);
    expect(text).toMatch(/floor "Level 2": the work moves onto it/);
    expect(text).toMatch(/collapse \(2 s\): the work leaves "Level 2" for good/);
    expect(r.notes.length).toBe(r.noteTimes.length);
  });

  it('is deterministic', () => {
    expect(JSON.stringify(directFourD(s.plan, s.model))).toBe(JSON.stringify(r));
  });

  it('no focus cues when the x-ray focus is off in the style', () => {
    const q = synth({ storeys: 2, seconds: 80, work: work(), style: { explode: 'floor', xrayFocus: false } });
    const rr = directFourD(q.plan, q.model);
    expect(of(rr, 'focus')).toEqual([]);
    expect(of(rr, 'explode').length).toBe(2);
  });

  it('auto and off do not make floor explodes, a one-storey model has nothing to explode', () => {
    for (const explode of ['off', 'auto'] as const) {
      const q = synth({ storeys: 2, seconds: 80, work: work(), style: { explode } });
      const rr = directFourD(q.plan, q.model);
      expect(rr.notes.some((n) => /floor "/.test(n))).toBe(false);
      expect(of(rr, 'focus').filter((f) => f.elements !== null && 'query' in f.elements)).toEqual([]);
    }
    const one = synth({ storeys: 1, seconds: 40, work: inner(0, 4, 30, 'A'), style: { explode: 'floor' } });
    const ro = directFourD(one.plan, one.model);
    expect(of(ro, 'explode')).toEqual([]);
    expect(ro.notes.join('\n')).toMatch(/nothing to explode apart/);
  });

  it('a floor with work for too short a time stays as it is, and the note says why', () => {
    const q = synth({ storeys: 2, seconds: 60, work: [...inner(0, 4, 30, 'A'), ...inner(1, 40, 43, 'B')], style: { explode: 'floor' } });
    const rr = directFourD(q.plan, q.model);
    expect(of(rr, 'explode').length).toBe(1);
    expect(rr.notes.join('\n')).toMatch(/floor "Level 2" has the work for only .*too short for an explode/);
  });

  it('floors that follow each other at once close first: the collapse ends before the next explode', () => {
    const q = synth({ storeys: 2, seconds: 80, work: [...inner(0, 4, 30, 'A'), ...inner(1, 30, 70, 'B')], style: { explode: 'floor' } });
    const rr = directFourD(q.plan, q.model);
    const e = of(rr, 'explode');
    const c = of(rr, 'collapse');
    expect(e.length).toBe(2);
    expect(e[1]!.at).toBeGreaterThanOrEqual(c[0]!.at + c[0]!.dur + 1 - 1e-6);
  });
});

// ---------------------------------------------------------------- the FZK-Haus sample

const file = (p: string): string => fileURLToPath(new URL(p, import.meta.url));
const schedule = parseXer(readFileSync(file('../public/samples/fzk-haus.xer')));
const config = JSON.parse(readFileSync(file('../public/samples/fzk-haus.4d.json'), 'utf8')) as FourDConfig;
const model = fromSidecar(JSON.parse(readFileSync(file('../public/models/fzk-haus.json'), 'utf8')), { identityKey: 'fzk-sample' });
const plan = buildPlan(schedule, linkSchedule(schedule, model, config, []), model, config.style);

describe('FZK-Haus sample: each floor apart', () => {
  const r = directFourD(plan, model);

  it('the sample asks for it', () => {
    expect(config.style.explode).toBe('floor');
    expect(plan.style.explode).toBe('floor');
  });

  it('explodes and collapses per floor: the ground floor, the roof storey, and back', () => {
    const ex = of(r, 'explode');
    const co = of(r, 'collapse');
    expect(ex.length).toBe(co.length);
    expect(ex.length).toBeGreaterThanOrEqual(2);
    const floors = r.notes.filter((n) => /floor "[^"]+": the work moves onto it/.test(n)).map((n) => /floor "([^"]+)"/.exec(n)![1]);
    expect(floors).toContain('Erdgeschoss');
    expect(floors).toContain('Dachgeschoss');
    expect(floors.length).toBe(ex.length);
    expect(floors.indexOf('Erdgeschoss')).toBeLessThan(floors.indexOf('Dachgeschoss'));
    // alternating, each collapse before the next explode
    const seq = r.cues.filter((c) => c.kind === 'explode' || c.kind === 'collapse');
    seq.forEach((c, i) => expect(c.kind).toBe(i % 2 === 0 ? 'explode' : 'collapse'));
    for (let i = 1; i < ex.length; i++) expect(ex[i]!.at).toBeGreaterThanOrEqual(co[i - 1]!.at + co[i - 1]!.dur + 1 - 1e-6);
    // the camera waits
    const blocks = [...ex, ...co].map(span);
    const cams = of(r, 'camera');
    for (const c of cams) for (const b of blocks) expect(overlap(span(c), b)).toBe(false);
    for (let i = 1; i < cams.length; i++) expect(cams[i]!.at - cams[i - 1]!.at).toBeGreaterThanOrEqual(3 - 1e-6);
    // the floors are named
    const caps = of(r, 'caption').map((c) => c.title);
    expect(caps).toContain('Erdgeschoss');
    expect(caps).toContain('Dachgeschoss');
  });

  it('the film round-trips through the script', () => {
    const text = scriptFromPlan(plan, r, { planName: 'Plan' });
    const c = compileScript(text, { plans: (n) => (n === 'Plan' ? plan : null) });
    expect(c.errors.filter((e) => e.severity === 'error')).toEqual([]);
    const count = (cues: readonly Cue[], k: string): number => cues.filter((x) => x.kind === k).length;
    expect(count(c.score!.cues, 'explode')).toBe(count(r.cues, 'explode'));
    expect(count(c.score!.cues, 'collapse')).toBe(count(r.cues, 'collapse'));
    expect(count(c.score!.cues, 'focus')).toBe(count(r.cues, 'focus'));
  });
});

// ---------------------------------------------------------------- the style in the .4d.json

describe('style fields in the .4d.json', () => {
  it('explode floor, fadeIn and issuesInFilm survive a save and a load', () => {
    const c = setStyle(emptyConfig(), { explode: 'floor', fadeIn: 1.5, issuesInFilm: true });
    const back = parseConfig(serializeConfig(c));
    expect(back.problems).toEqual([]);
    expect(back.config!.style.explode).toBe('floor');
    expect(back.config!.style.fadeIn).toBe(1.5);
    expect(back.config!.style.issuesInFilm).toBe(true);
  });

  it('fadeIn 0 (at once) is kept; unset stays unset (the default rule)', () => {
    expect(parseConfig(serializeConfig(setStyle(emptyConfig(), { fadeIn: 0 }))).config!.style.fadeIn).toBe(0);
    const plain = parseConfig(serializeConfig(emptyConfig())).config!.style;
    expect(plain.fadeIn).toBeUndefined();
    expect(plain.issuesInFilm).toBeUndefined();
    expect(plain.explode).toBe(DEFAULT_STYLE.explode);
  });

  it('wrong values are listed and left out', () => {
    const text = JSON.stringify({ ...emptyConfig(), style: { ...DEFAULT_STYLE, explode: 'sideways', fadeIn: -2, issuesInFilm: 'yes' } });
    const back = parseConfig(text);
    expect(back.problems.length).toBe(3);
    expect(back.config!.style.explode).toBe('auto');
    expect(back.config!.style.fadeIn).toBeUndefined();
    expect(back.config!.style.issuesInFilm).toBeUndefined();
  });

  it('the plan keeps the style, and the director script says the fade only when it is set', () => {
    const base = synth({ storeys: 1, seconds: 40, work: inner(0, 4, 30, 'A') });
    const with1 = { ...base.plan, style: { ...base.plan.style, fadeIn: 1.5 } };
    const t1 = scriptFromPlan(with1, directFourD(with1, base.model), { planName: 'P' });
    expect(t1).toMatch(/^schedule "P" view planned from "[^"]+" to "[^"]+" over 40 seconds fade 1\.5 seconds$/m);
    const t0 = scriptFromPlan(base.plan, directFourD(base.plan, base.model), { planName: 'P' });
    expect(t0).not.toMatch(/ fade /);
    const zero = { ...base.plan, style: { ...base.plan.style, fadeIn: 0 } };
    expect(scriptFromPlan(zero, directFourD(zero, base.model), { planName: 'P' })).toMatch(/over 40 seconds fade 0 seconds$/m);
  });
});
