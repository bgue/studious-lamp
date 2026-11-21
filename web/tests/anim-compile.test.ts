import { describe, expect, it } from 'vitest';
import { compileFlyThrough, keyframeTimes, migrateLegacy, newFlyThrough, newKeyframe, parseFlyDoc, serializeFlyDoc, visibilityChange } from '../src/anim/flythrough';
import type { FlyThrough } from '../src/anim/flythrough';
import type { Cue } from '../src/anim/score';
import type { SavedView } from '../src/views/model';

function view(name: string, x: number, extra: Partial<SavedView> = {}): SavedView {
  return {
    id: `v-${name}`,
    name,
    created: '2026-01-01T00:00:00.000Z',
    updated: '2026-01-01T00:00:00.000Z',
    camera: { position: [x, 2, 10], target: [x, 0, 0], up: [0, 1, 0], fov: 50, ortho: false },
    selection: [],
    params: {},
    ...extra,
  };
}

function ft(views: SavedView[], opts: Partial<FlyThrough> = {}, kopts: Array<Partial<Parameters<typeof newKeyframe>[1]>> = []): FlyThrough {
  const f = newFlyThrough('Test', 2);
  Object.assign(f, opts);
  views.forEach((v, i) => f.keyframes.push(newKeyframe(v, kopts[i] ?? {})));
  return f;
}

const of = <K extends Cue['kind']>(cues: Cue[], kind: K): Array<Extract<Cue, { kind: K }>> => cues.filter((c) => c.kind === kind) as never;

describe('compileFlyThrough: timing', () => {
  it('has no cues for no keyframes and a view cue for one', () => {
    expect(compileFlyThrough(ft([])).cues).toEqual([]);
    const one = compileFlyThrough(ft([view('a', 0)]));
    expect(of(one.cues, 'cameraPath')).toHaveLength(0);
    expect(of(one.cues, 'view')).toHaveLength(1);
  });

  it('uses a constant speed by arc length by default: the times follow the distance', () => {
    const f = ft([view('a', 0), view('b', 10), view('c', 40)], { speed: 5 });
    const tm = keyframeTimes(f);
    expect(tm.arrive[0]).toBe(0);
    // 10 m at 5 m/s, then 30 m at 5 m/s: the second move takes three times as long.
    expect(tm.travel[1]).toBeCloseTo(2, 1);
    expect(tm.travel[2]).toBeCloseTo(6, 1);
    const path = of(compileFlyThrough(f).cues, 'cameraPath')[0]!;
    expect(path.times).toEqual(tm.arrive);
    expect(path.poses).toHaveLength(3);
  });

  it('uses fixed seconds per segment when asked, and a keyframe travel overrides both', () => {
    const f = ft([view('a', 0), view('b', 10), view('c', 40)], { timing: 'seconds', segmentS: 3 });
    expect(keyframeTimes(f).travel).toEqual([0, 3, 3]);
    f.keyframes[2]!.travel = 7;
    expect(keyframeTimes(f).travel).toEqual([0, 3, 7]);
    const g = ft([view('a', 0), view('b', 10)], { speed: 5 });
    g.keyframes[1]!.travel = 9;
    expect(keyframeTimes(g).travel[1]).toBe(9);
  });

  it('takes the turn of the view into account when the camera only turns, and has a minimum travel time', () => {
    const a = view('a', 0);
    const b = view('b', 0, { camera: { position: [0, 2, 10], target: [10, 2, 10], up: [0, 1, 0], fov: 50, ortho: false } });
    const f = ft([a, b], { speed: 5 });
    expect(keyframeTimes(f).travel[1]).toBeGreaterThan(0.5);
    const same = ft([view('a', 0), view('b', 0)], { speed: 5 });
    expect(keyframeTimes(same).travel[1]).toBe(0.5);
  });

  it('puts a hold on the timeline: a repeated pose with its own time', () => {
    const f = ft([view('a', 0), view('b', 10), view('c', 20)], { speed: 5 }, [{}, { hold: 3 }, {}]);
    const tm = keyframeTimes(f);
    expect(tm.arrive[1]).toBeCloseTo(2, 1);
    expect(tm.depart[1]).toBeCloseTo(5, 1);
    expect(tm.arrive[2]).toBeCloseTo(7, 1);
    const s = compileFlyThrough(f);
    const path = of(s.cues, 'cameraPath')[0]!;
    expect(path.poses).toHaveLength(4);
    expect(path.times[1]).toBeCloseTo(2, 1);
    expect(path.times[2]).toBeCloseTo(5, 1);
    expect(path.poses[1]).toEqual(path.poses[2]);
    expect(s.duration).toBeCloseTo(7, 1);
    expect(path.dur).toBeCloseTo(7, 1);
  });

  it('adds the hold of the last keyframe to the duration and passes the ease flags on', () => {
    const f = ft([view('a', 0), view('b', 10)], { speed: 5 }, [{ ease: false }, { hold: 4, ease: true }]);
    const s = compileFlyThrough(f);
    expect(s.duration).toBeCloseTo(2 + 4, 1);
    const path = of(s.cues, 'cameraPath')[0]!;
    expect(path.easeAt).toEqual([false, true, true]);
    expect(path.ease).toBe('inOut');
  });

  it('keeps looking at the selection when asked', () => {
    const f = ft([view('a', 0, { selection: ['G1'] }), view('b', 10)], { lookAtSelection: true });
    const s = compileFlyThrough(f, { selectionCenter: (g) => (g[0] === 'G1' ? [7, 8, 9] : null) });
    const path = of(s.cues, 'cameraPath')[0]!;
    expect(path.poses[0]!.target).toEqual([7, 8, 9]);
    expect(path.poses[1]!.target).toEqual([10, 0, 0]);
    const plain = compileFlyThrough(ft([view('a', 0, { selection: ['G1'] }), view('b', 10)]), { selectionCenter: () => [7, 8, 9] });
    expect(of(plain.cues, 'cameraPath')[0]!.poses[0]!.target).toEqual([0, 0, 0]);
  });
});

describe('compileFlyThrough: view, selection, caption cues', () => {
  it('emits a view cue per keyframe: instant for the first, over the travel for the others, switching at switchAt', () => {
    const f = ft([view('a', 0, { params: { xray: true } }), view('b', 10, { params: { sightlines: { alphaMax: 0.5 } }, preset: 'p1', exploded: true })], { speed: 5 }, [{}, { switchAt: 'mid' }]);
    const v = of(compileFlyThrough(f).cues, 'view');
    expect(v).toHaveLength(2);
    expect(v[0]!.at).toBe(0);
    expect(v[0]!.dur).toBe(0);
    expect(v[1]!.at).toBe(0);
    expect(v[1]!.dur).toBeCloseTo(2, 1);
    expect(v[1]!.switchAt).toBe('mid');
    expect(v[1]!.state.params).toEqual({ sightlines: { alphaMax: 0.5 } });
    expect(v[1]!.state.presetId).toBe('p1');
    expect(v[1]!.state.explode).toBe(true);
    expect(v[0]!.state.explode).toBe(false);
  });

  it('starts the selection shortly before arrival, not after', () => {
    const f = ft([view('a', 0), view('b', 10, { selection: ['G1', 'G2'] })], { speed: 5 });
    const sel = of(compileFlyThrough(f).cues, 'select');
    const arrive = keyframeTimes(f).arrive[1]!;
    const s = sel.find((c) => c.elements)!;
    expect(s.at).toBeLessThan(arrive);
    expect(s.at).toBeGreaterThan(arrive - 1);
    expect(s.elements).toEqual({ globalIds: ['G1', 'G2'] });
    // No new select cue for an unchanged selection; the first keyframe always sets it.
    const same = of(compileFlyThrough(ft([view('a', 0, { selection: ['G1'] }), view('b', 10, { selection: ['G1'] })])).cues, 'select');
    expect(same).toHaveLength(1);
    expect(sel.find((c) => c.at === 0)!.elements).toBeNull();
  });

  it('adds a caption cue at arrival that lasts as long as the hold (else 2.5 s)', () => {
    const f = ft([view('a', 0), view('b', 10), view('c', 20)], { speed: 5 }, [{}, { hold: 4, caption: { title: 'Pump room', text: 'Level 2' } }, { caption: { text: 'End' } }]);
    const caps = of(compileFlyThrough(f).cues, 'caption');
    expect(caps).toHaveLength(2);
    expect(caps[0]).toMatchObject({ title: 'Pump room', text: 'Level 2', dur: 4 });
    expect(caps[0]!.at).toBeCloseTo(2, 1);
    expect(caps[1]).toMatchObject({ text: 'End', dur: 2.5 });
    expect('title' in caps[1]!).toBe(false);
  });
});

describe('compileFlyThrough: visibility and fades', () => {
  const hide = (ids: string[]) => ({ hides: { mode: 'hide' as const, ids } });

  it('fades elements that differ over the last 40 % of the travel by default', () => {
    const f = ft([view('a', 0, hide(['H1', 'H2'])), view('b', 10, hide(['H2', 'H3']))], { speed: 5 });
    const vis = of(compileFlyThrough(f).cues, 'visibility');
    expect(vis).toHaveLength(2);
    expect(vis[0]!.at).toBe(0);
    expect(vis[0]!.dur).toBe(0);
    expect(vis[0]).toMatchObject({ showAll: true, hide: { globalIds: ['H1', 'H2'] } });
    const fade = vis[1]!;
    const travel = 2;
    expect(fade.dur).toBeCloseTo(travel * 0.4, 6);
    expect(fade.at).toBeCloseTo(travel - travel * 0.4, 6);
    expect(fade.hide).toEqual({ globalIds: ['H3'] });
    expect(fade.show).toEqual({ globalIds: ['H1'] });
  });

  it('honours the fade length and the fade switch (off: an instant change at switchAt)', () => {
    const f = ft([view('a', 0), view('b', 10, hide(['H1']))], { speed: 5 }, [{}, { fadeFraction: 0.8 }]);
    const fade = of(compileFlyThrough(f).cues, 'visibility').find((c) => c.dur > 0)!;
    expect(fade.dur).toBeCloseTo(1.6, 6);
    const off = ft([view('a', 0), view('b', 10, hide(['H1']))], { speed: 5 }, [{}, { fade: false, switchAt: 'mid' }]);
    const inst = of(compileFlyThrough(off).cues, 'visibility').find((c) => c.at > 0)!;
    expect(inst.dur).toBe(0);
    expect(inst.at).toBeCloseTo(1, 6);
  });

  it('emits no visibility cue when two keyframes hide the same elements (the first still sets the state)', () => {
    const f = ft([view('a', 0, hide(['H1'])), view('b', 10, hide(['H1']))]);
    expect(of(compileFlyThrough(f).cues, 'visibility')).toHaveLength(1);
  });

  it('describes isolate changes: only the elements that differ, or the target when one side hides and the other isolates', () => {
    const iso = (ids: string[]) => ({ hides: { mode: 'show' as const, ids } });
    expect(visibilityChange(view('a', 0, iso(['A', 'B'])), view('b', 0, iso(['B', 'C'])))).toEqual({ hide: { globalIds: ['A'] }, show: { globalIds: ['C'] } });
    expect(visibilityChange(view('a', 0, hide(['A'])), view('b', 0, iso(['B'])))).toEqual({ isolate: { globalIds: ['B'] } });
    expect(visibilityChange(view('a', 0, iso(['B'])), view('b', 0))).toEqual({ showAll: true });
    expect(visibilityChange(view('a', 0), view('b', 0))).toBeNull();
  });
});

describe('legacy migration and storage', () => {
  const legacy = JSON.stringify({
    schema: 'xray-flythrough/1',
    model: 'building',
    segmentSeconds: 4,
    keyframes: [
      { position: [1, 2, 3], target: [0, 0, 0], selection: ['G1'], toggles: { reveal: true, sweep: false, depthGrade: true, bloom: false, edgeGlow: true, ao: true, vignette: false }, name: 'First' },
      { position: [4, 5, 6], target: [1, 1, 1], selection: [], toggles: {} },
      { position: 'bad' },
    ],
  });

  it('imports the camera, selection and the 7 toggles as a fly-through named Imported', () => {
    const f = migrateLegacy(legacy, 45)!;
    expect(f.name).toBe('Imported');
    expect(f.timing).toBe('seconds');
    expect(f.segmentS).toBe(4);
    expect(f.keyframes).toHaveLength(2);
    const k = f.keyframes[0]!;
    expect(k.name).toBe('First');
    expect(k.view.camera).toMatchObject({ position: [1, 2, 3], target: [0, 0, 0], fov: 45 });
    expect(k.view.selection).toEqual(['G1']);
    expect(k.view.params).toEqual({
      cinematic: { reveal: true, sweep: { enabled: false }, grade: { enabled: true }, bloom: false, edgeGlow: true },
      post: { ao: true, vignette: false },
    });
    expect(f.keyframes[1]!.name).toBe('Keyframe 2');
    expect(k.fade).toBe(false);
  });

  it('gives nothing for empty or broken input, and reads a bare array', () => {
    expect(migrateLegacy(null)).toBeNull();
    expect(migrateLegacy('nope')).toBeNull();
    expect(migrateLegacy('[]')).toBeNull();
    expect(migrateLegacy(JSON.stringify([{ position: [0, 0, 0], target: [0, 0, 1], selection: [], toggles: {} }]))!.keyframes).toHaveLength(1);
  });

  it('round-trips a document and drops bad entries', () => {
    const a = ft([view('a', 0), view('b', 10)], { speed: 3, lookAtSelection: true, loop: true }, [{}, { hold: 2, caption: { title: 'T', text: 'x' }, travel: 4 }]);
    const text = serializeFlyDoc({ schema: 'xray-flythroughs/1', flythroughs: [a], active: a.id });
    const doc = parseFlyDoc(text)!;
    expect(doc.flythroughs).toHaveLength(1);
    const b = doc.flythroughs[0]!;
    expect(b.keyframes[1]).toMatchObject({ hold: 2, travel: 4, caption: { title: 'T', text: 'x' } });
    expect(b.lookAtSelection).toBe(true);
    expect(b.loop).toBe(true);
    expect(doc.active).toBe(a.id);
    expect(parseFlyDoc('{"schema":"xray-flythroughs/2","flythroughs":[]}')).toBeNull();
    expect(parseFlyDoc('x')).toBeNull();
    const bad = parseFlyDoc(JSON.stringify({ schema: 'xray-flythroughs/1', flythroughs: [{ name: 'n', keyframes: [{ view: { name: 'x' } }, null] }, 5] }))!;
    expect(bad.flythroughs[0]!.keyframes).toHaveLength(0);
  });

  it('can leave the thumbnails out of an export', () => {
    const a = ft([view('a', 0, { thumb: 'data:image/jpeg;base64,AAAA' })]);
    const doc = { schema: 'xray-flythroughs/1' as const, flythroughs: [a], active: a.id };
    expect(serializeFlyDoc(doc, true)).toContain('data:image/jpeg');
    expect(serializeFlyDoc(doc, false)).not.toContain('data:image/jpeg');
  });
});
