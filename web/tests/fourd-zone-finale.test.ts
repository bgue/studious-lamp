// The 4D director: a saved view per storey (style.zoneCameras) and the closing dolly / orbit (style.finale).
import { describe, expect, it } from 'vitest';
import { directFourD, finaleSeconds } from '../src/schedule/director';
import type { Cue } from '../src/anim/score';
import { el, synth } from './director-helpers';
import type { Work } from './director-helpers';

type CamCue = Extract<Cue, { kind: 'camera' }>;
const cams = (cues: Cue[]): CamCue[] => cues.filter((c) => c.kind === 'camera') as CamCue[];
const inner = (s: number, from: number, to: number, task: string): Work[] => [4, 5, 6, 7].map((k) => ({ el: el(s, k), from, to, task }));
const work = (): Work[] => [...inner(0, 0, 30, 'A'), ...inner(1, 28, 60, 'B')];

describe('director: camera per floor', () => {
  const base = synth({ storeys: 2, seconds: 60, work: work() });
  const storey0 = base.model.elements.find((e) => e.storey !== undefined)!.storey!;

  it('flies to the saved view while the work lies on that storey, and says so', () => {
    const s = synth({ storeys: 2, seconds: 60, work: work() });
    s.plan.style = { ...s.plan.style, zoneCameras: { [storey0]: 'EG south' } };
    const r = directFourD(s.plan, s.model);
    const views = cams(r.cues).filter((c) => 'view' in c.to);
    expect(views.length).toBeGreaterThanOrEqual(1);
    expect(views.every((c) => (c.to as { view: string }).view === 'EG south')).toBe(true);
    expect(r.notes.some((n) => n.includes(`camera for ${storey0}: saved view 'EG south'`))).toBe(true);
    const all = cams(r.cues);
    for (let i = 1; i < all.length; i++) expect(all[i]!.at - all[i - 1]!.at).toBeGreaterThanOrEqual(3 - 1e-6);
  });

  it('without a zone camera the same plan has no view cue', () => {
    const r = directFourD(base.plan, base.model);
    expect(cams(r.cues).some((c) => 'view' in c.to)).toBe(false);
  });
});

describe('director: finale', () => {
  const run = (finale: 'none' | 'dolly' | 'orbit', camera: 'director' | 'fixed' = 'director') => {
    const s = synth({ storeys: 2, seconds: 60, work: work() });
    s.plan.style = { ...s.plan.style, finale, camera };
    return directFourD(s.plan, s.model);
  };

  it('none adds nothing and reports no longer duration', () => {
    const r = run('none');
    expect(r.duration).toBeUndefined();
    expect(r.notes.some((n) => n.includes('finale'))).toBe(false);
  });

  it('dolly: clear focus, a 6 s dolly-in, a 90 degree 8 s orbit with a caption, after the last work', () => {
    const r = run('dolly');
    const dolly = cams(r.cues).filter((c) => 'frame' in c.to && c.at >= 60 - 1e-6);
    const orbit = cams(r.cues).filter((c) => 'orbitDeg' in c.to && c.at >= 60 - 1e-6);
    expect(dolly).toHaveLength(1);
    expect(dolly[0]!.dur).toBe(6);
    expect(dolly[0]!.ease).toBe('inOut');
    expect(orbit).toHaveLength(1);
    expect((orbit[0]!.to as { orbitDeg: number }).orbitDeg).toBe(90);
    expect(orbit[0]!.dur).toBe(8);
    expect(orbit[0]!.at).toBeGreaterThanOrEqual(dolly[0]!.at + 6 - 1e-6);
    const cap = r.cues.filter((c) => c.kind === 'caption' && c.at >= 60 - 1e-6);
    expect(cap).toHaveLength(1);
    expect(r.notes.some((n) => n.includes('focus'))).toBe(true);
    expect(r.duration).toBeGreaterThanOrEqual(60 + finaleSeconds('dolly') - 1e-6);
    expect(r.duration).toBeCloseTo(orbit[0]!.at + 8, 3);
    expect(r.notes.some((n) => n.includes('finale "dolly"'))).toBe(true);
    expect(r.notes.some((n) => n.includes('90 degree orbit'))).toBe(true);
  });

  it('orbit: only the orbit, 8 s more', () => {
    const r = run('orbit');
    expect(cams(r.cues).filter((c) => 'frame' in c.to && c.at >= 60 - 1e-6)).toHaveLength(0);
    expect(cams(r.cues).filter((c) => 'orbitDeg' in c.to && c.at >= 60 - 1e-6)).toHaveLength(1);
    expect(r.duration).toBeGreaterThanOrEqual(68 - 1e-6);
  });

  it('a fixed camera gets no finale and a note that says why', () => {
    const r = run('dolly', 'fixed');
    expect(r.duration).toBeUndefined();
    expect(r.notes.some((n) => n.includes('finale "dolly" left out'))).toBe(true);
  });
});
