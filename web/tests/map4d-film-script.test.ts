// The 4D film as a script (src/map4d/filmScript.ts): the name, the text with and without the camera director, and that it compiles to the same film.
import { describe, expect, it } from 'vitest';
import { compileScript } from '../src/anim/script/compiler';
import { directFourD } from '../src/schedule/director';
import { filmName, filmScript } from '../src/map4d/filmScript';
import { synth } from './director-helpers';
import type { Work } from './director-helpers';

const work = (): Work[] => Array.from({ length: 24 }, (_v, i) => ({ el: i, from: 2 + i * 3, to: 8 + i * 3, task: `A${i}` }));

describe('filmName', () => {
  it('takes the project name, then the short name, then the file name', () => {
    expect(filmName('FZK Haus', 'FZK')).toBe('FZK Haus');
    expect(filmName(undefined, 'FZK-HAUS')).toBe('FZK-HAUS');
    expect(filmName('', undefined, 'job.xer')).toBe('job');
    expect(filmName(undefined, undefined)).toBe('4D film');
    expect(filmName('  a   b  ', undefined)).toBe('a b');
    expect(filmName('x'.repeat(100), undefined).length).toBe(60);
  });
});

describe('filmScript', () => {
  const b = synth({ storeys: 4, seconds: 90, work: work(), milestones: [{ name: 'Frame complete', at: 40 }] });

  it('writes the director\'s moves and compiles against the registered plan', () => {
    const res = directFourD(b.plan, b.model);
    const out = filmScript(b.plan, 'Tower', res);
    expect(out.text).toMatch(/^-- made from the 4D film of Tower/);
    expect(out.text).toContain('schedule "Tower"');
    expect(out.lines).toBe(out.text.replace(/\n+$/, '').split('\n').length);
    expect(out.lines).toBeGreaterThan(10);
    const c = compileScript(out.text, { plans: (n) => (n === 'Tower' ? b.plan : null) });
    expect(c.errors.filter((e) => e.severity === 'error')).toEqual([]);
  });

  it('without a director: the schedule statement and a note that the camera stays put', () => {
    const out = filmScript(b.plan, 'Tower', null, 'the camera director is not part of this build.');
    expect(out.text).toContain('-- The camera stays put: the camera director is not part of this build.');
    expect(out.text).toContain('schedule "Tower"');
    expect(out.text).not.toMatch(/^fly to/m);
    const c = compileScript(out.text, { plans: (n) => (n === 'Tower' ? b.plan : null) });
    expect(c.errors.filter((e) => e.severity === 'error')).toEqual([]);
    expect(c.score!.cues.some((q) => q.kind === 'schedule4d')).toBe(true);
  });
});
