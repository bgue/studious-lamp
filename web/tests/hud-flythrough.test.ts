import { describe, expect, it } from 'vitest';
import { compileFlyThrough, newFlyThrough, newKeyframe, parseFlyDoc, serializeFlyDoc, DEFAULT_CAPTION_S } from '../src/anim/flythrough';
import { FlyStore } from '../src/anim/store';
import { MemoryStorage } from '../src/selectionSets';
import type { Cue } from '../src/anim/score';
import type { SavedView } from '../src/views/model';

function view(name: string, x: number, selection: string[] = []): SavedView {
  return {
    id: `v-${name}`,
    name,
    created: 'c',
    updated: 'u',
    camera: { position: [x, 2, 10], target: [x, 0, 0], up: [0, 1, 0], fov: 50, ortho: false },
    selection,
    params: {},
  };
}
const of = <K extends Cue['kind']>(cues: Cue[], kind: K): Array<Extract<Cue, { kind: K }>> => cues.filter((c) => c.kind === kind) as never;

describe('keyframe labels and hover card compile to cues', () => {
  it('compiles "label the selection" to a label cue with the selection, the fields and the length of a caption', () => {
    const f = newFlyThrough('T', 2);
    f.keyframes.push(newKeyframe(view('a', 0)));
    f.keyframes.push(newKeyframe(view('b', 10, ['g1', 'g2']), { hold: 4, labels: { fields: ['name', 'Pset_X.Y'] } }));
    const s = compileFlyThrough(f);
    const l = of(s.cues, 'label');
    expect(l).toHaveLength(1);
    expect(l[0]!.at).toBeCloseTo(5, 3);
    expect(l[0]).toMatchObject({ dur: 4, elements: { globalIds: ['g1', 'g2'] }, fields: ['name', 'Pset_X.Y'] });
    expect(of(s.cues, 'hover')).toHaveLength(0);
  });
  it('compiles the hover card for the first selected element and falls back to 2.5 s without a hold', () => {
    const f = newFlyThrough('T', 2);
    f.keyframes.push(newKeyframe(view('a', 0, ['g9', 'g8']), { hover: true, labels: { fields: [] } }));
    const s = compileFlyThrough(f);
    expect(of(s.cues, 'hover')[0]).toMatchObject({ at: 0, dur: DEFAULT_CAPTION_S, elements: { globalIds: ['g9'] } });
    expect(of(s.cues, 'label')[0]!.fields).toEqual(['name', 'class', 'storey']);
    expect(s.duration).toBeGreaterThanOrEqual(DEFAULT_CAPTION_S);
  });
  it('makes no cue without a selection', () => {
    const f = newFlyThrough('T', 2);
    f.keyframes.push(newKeyframe(view('a', 0), { hover: true, labels: { fields: ['name'] } }));
    const s = compileFlyThrough(f);
    expect(of(s.cues, 'label')).toHaveLength(0);
    expect(of(s.cues, 'hover')).toHaveLength(0);
  });
});

describe('storing the options', () => {
  it('sets, clears and sanitises labels and hover of a keyframe', () => {
    const s = new FlyStore(new MemoryStorage());
    s.load('k', 'm');
    const f = s.create('T');
    s.add(f, view('a', 0, ['g']));
    s.update(f, 0, { labels: { fields: [' name ', 'name', '', 'Pset_A.B'] }, hover: true });
    expect(f.keyframes[0]!.labels).toEqual({ fields: ['name', 'Pset_A.B'] });
    expect(f.keyframes[0]!.hover).toBe(true);
    s.update(f, 0, { labels: { fields: [] } });
    expect(f.keyframes[0]!.labels).toEqual({ fields: ['name', 'class', 'storey'] });
    s.update(f, 0, { labels: null, hover: false });
    expect(f.keyframes[0]!.labels).toBeUndefined();
    expect(f.keyframes[0]!.hover).toBeUndefined();
  });
  it('round-trips labels, hover and the HUD settings through the stored document', () => {
    const mem = new MemoryStorage();
    const s = new FlyStore(mem);
    s.load('k', 'm');
    const f = s.create('T');
    s.add(f, view('a', 0, ['g']), undefined, { labels: { fields: ['class'] }, hover: true });
    expect(s.hud).toEqual({ progress: true, compass: false, scaleBar: false, labelSize: 12, captionPosition: 'bottom', scheduleDate: true, sCurve: true, activities: true, milestones: true, legend: true });
    s.setHud({ compass: true, labelSize: 18, captionPosition: 'top' });
    const again = new FlyStore(mem);
    again.load('k', 'm');
    expect(again.active!.keyframes[0]!.labels).toEqual({ fields: ['class'] });
    expect(again.active!.keyframes[0]!.hover).toBe(true);
    expect(again.hud).toMatchObject({ compass: true, labelSize: 18, captionPosition: 'top', progress: true });
    const doc = parseFlyDoc(serializeFlyDoc(again.doc));
    expect(doc!.hud!.labelSize).toBe(18);
  });
  it('keeps the HUD settings out of the params of a view and the per-model settings apart', () => {
    const mem = new MemoryStorage();
    const a = new FlyStore(mem);
    a.load('one', 'm');
    a.create('T');
    a.setHud({ progress: false });
    const b = new FlyStore(mem);
    b.load('two', 'm');
    expect(b.hud.progress).toBe(true);
    expect(JSON.stringify([...mem.map.entries()])).not.toContain('params');
  });
  it('repairs bad stored HUD settings', () => {
    const d = parseFlyDoc(JSON.stringify({ schema: 'xray-flythroughs/1', flythroughs: [], hud: { progress: 'x', labelSize: 'big' } }));
    expect(d!.hud).toEqual({ progress: true, compass: false, scaleBar: false, labelSize: 12, captionPosition: 'bottom', scheduleDate: true, sCurve: true, activities: true, milestones: true, legend: true });
  });
});
