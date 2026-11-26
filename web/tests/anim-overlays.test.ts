// Issue pins and drawings while a score plays: the default, the cues, the restore (pure part), and the player handing its options to the host.
import { describe, expect, it } from 'vitest';
import { HIDE_DRAWINGS_CLASS, HIDE_ISSUES_CLASS, OverlayGate, applyOverlayCue, applyOverlaysToDom, overlayCss, overlayDefault } from '../src/anim/overlays';
import type { OverlayState } from '../src/anim/overlays';
import { ScorePlayer } from '../src/anim/player';
import type { CueRunner, PlayerHost } from '../src/anim/player';
import { SCORE_SCHEMA } from '../src/anim/score';
import type { Cue, PlayOptions, Score } from '../src/anim/score';
import { DEFAULT_STYLE } from '../src/schedule/types';
import { fakePlan } from './director-helpers';

const cue = (c: Partial<Extract<Cue, { kind: 'overlays' }>>): Extract<Cue, { kind: 'overlays' }> => ({ kind: 'overlays', at: 0, dur: 0, ...c });
const sched = (plan: ReturnType<typeof fakePlan> | { name: string }): Cue => ({ kind: 'schedule4d', at: 0, dur: 10, plan });
const score = (cues: Cue[]): Score => ({ schema: SCORE_SCHEMA, duration: 10, cues });

describe('overlayDefault', () => {
  it('hides both pins and drawings unless told otherwise', () => {
    expect(overlayDefault(score([sched(fakePlan())]))).toEqual({ issues: false, drawings: false });
    expect(overlayDefault(score([]), {})).toEqual({ issues: false, drawings: false });
  });
  it('PlayOptions.overlays overrides, field by field', () => {
    expect(overlayDefault(score([]), { issues: true })).toEqual({ issues: true, drawings: false });
    expect(overlayDefault(score([]), { drawings: true })).toEqual({ issues: false, drawings: true });
    expect(overlayDefault(score([]), { issues: false, drawings: false })).toEqual({ issues: false, drawings: false });
  });
  it('a 4D plan whose style says issuesInFilm keeps them, and the option still wins', () => {
    const on = fakePlan({ style: { ...DEFAULT_STYLE, issuesInFilm: true } });
    const planOf = (c: Extract<Cue, { kind: 'schedule4d' }>) => ('schema' in c.plan ? c.plan : null);
    expect(overlayDefault(score([sched(on)]), undefined, planOf)).toEqual({ issues: true, drawings: true });
    expect(overlayDefault(score([sched(on)]), { issues: false }, planOf)).toEqual({ issues: false, drawings: true });
    expect(overlayDefault(score([sched(fakePlan())]), undefined, planOf)).toEqual({ issues: false, drawings: false });
    // a plan the resolver does not know changes nothing
    expect(overlayDefault(score([sched({ name: 'x' })]), undefined, () => null)).toEqual({ issues: false, drawings: false });
  });
});

describe('overlay cues and the gate', () => {
  it('a cue changes only the fields it names', () => {
    const cur: OverlayState = { issues: false, drawings: false };
    expect(applyOverlayCue(cur, cue({ issues: true }))).toEqual({ issues: true, drawings: false });
    expect(applyOverlayCue({ issues: true, drawings: true }, cue({ drawings: false }))).toEqual({ issues: true, drawings: false });
    expect(applyOverlayCue(cur, cue({}))).toEqual(cur);
  });

  it('hides at the start, follows the cues, puts everything back at the end', () => {
    const seen: OverlayState[] = [];
    const g = new OverlayGate((s) => seen.push(s));
    expect(g.active).toBe(false);
    g.begin({ issues: false, drawings: false });
    expect(g.active).toBe(true);
    g.cue(cue({ issues: true }));
    g.cue(cue({ issues: true })); // no change: nothing applied
    g.cue(cue({ drawings: true, issues: false }));
    g.end();
    g.end(); // a second end does nothing
    expect(seen).toEqual([
      { issues: false, drawings: false },
      { issues: true, drawings: false },
      { issues: false, drawings: true },
      { issues: true, drawings: true },
    ]);
    expect(g.active).toBe(false);
  });

  it('cues outside a play are ignored', () => {
    const seen: OverlayState[] = [];
    const g = new OverlayGate((s) => seen.push(s));
    g.cue(cue({ issues: true }));
    expect(seen).toEqual([]);
  });

  it('a begin while running (seek, loop) starts from the default again', () => {
    const seen: OverlayState[] = [];
    const g = new OverlayGate((s) => seen.push(s));
    g.begin({ issues: false, drawings: false });
    g.cue(cue({ issues: true }));
    g.begin({ issues: false, drawings: false });
    expect(g.current).toEqual({ issues: false, drawings: false });
    expect(seen.at(-1)).toEqual({ issues: false, drawings: false });
  });
});

describe('overlays in the page', () => {
  const fakeDoc = () => {
    const classes = new Set<string>();
    const nodes = new Map<string, { id: string; textContent: string }>();
    const doc = {
      getElementById: (id: string) => nodes.get(id) ?? null,
      createElement: () => ({ id: '', textContent: '' }),
      head: { appendChild: (n: { id: string; textContent: string }) => nodes.set(n.id, n) },
      documentElement: { classList: { toggle: (c: string, on: boolean) => (on ? classes.add(c) : classes.delete(c)) } },
    };
    return { doc: doc as unknown as Document, classes, nodes };
  };

  it('puts the hide classes on while hidden and takes them off when shown (exactly the state before)', () => {
    const { doc, classes, nodes } = fakeDoc();
    expect(classes.size).toBe(0);
    applyOverlaysToDom({ issues: false, drawings: false }, doc);
    expect([...classes].sort()).toEqual([HIDE_DRAWINGS_CLASS, HIDE_ISSUES_CLASS].sort());
    applyOverlaysToDom({ issues: true, drawings: false }, doc);
    expect([...classes]).toEqual([HIDE_DRAWINGS_CLASS]);
    applyOverlaysToDom({ issues: true, drawings: true }, doc);
    expect(classes.size).toBe(0);
    expect(nodes.size).toBe(1); // the style element is made once
  });

  it('the style hides the layers of the issue pins and of the drawings', () => {
    const css = overlayCss();
    expect(css).toContain('g[data-layer="bcf-markup"]');
    expect(css).toContain('g[data-layer="markup"]');
    expect(css).toContain('g[data-layer="sheet-sketches"]');
  });
});

describe('the player hands its options to the host', () => {
  it('begin gets the play options (also after a seek)', () => {
    const calls: Array<PlayOptions | undefined> = [];
    const host: PlayerHost = {
      begin: (_s, o) => void calls.push(o),
      start: (): CueRunner | null => ({ update: () => undefined }),
      restore: () => undefined,
      finish: () => undefined,
    };
    const p = new ScorePlayer(host);
    const opts: PlayOptions = { overlays: { issues: true } };
    expect(p.play(score([cue({ at: 0, drawings: true })]), opts)).toBe(true);
    p.seek(2);
    expect(calls.length).toBe(2);
    expect(calls.every((o) => o?.overlays?.issues === true)).toBe(true);
    p.stop();
  });
});
