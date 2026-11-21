import { describe, expect, it } from 'vitest';
import { ScorePlayer } from '../src/anim/player';
import type { CueRunner, PlayerHost } from '../src/anim/player';
import { SCORE_SCHEMA } from '../src/anim/score';
import type { Cue, Score } from '../src/anim/score';
import { pathGeometry } from '../src/anim/overlay';

class FakeHost implements PlayerHost {
  log: string[] = [];
  progress = new Map<number, number[]>();
  skip = new Set<string>();
  begins = 0;
  restored: boolean[] = [];
  finishes = 0;
  flushes: number[] = [];
  begin(): void {
    this.begins++;
    this.log.push('begin');
  }
  start(cue: Cue, index: number): CueRunner | null {
    if (this.skip.has(cue.kind)) return null;
    this.log.push(`start ${index}:${cue.kind}`);
    const arr: number[] = [];
    this.progress.set(index, arr);
    return {
      update: (p) => arr.push(p),
      end: () => this.log.push(`end ${index}`),
    };
  }
  restore(keepCamera: boolean): void {
    this.restored.push(keepCamera);
    this.log.push('restore');
  }
  finish(): void {
    this.finishes++;
  }
  flush(t: number): void {
    this.flushes.push(t);
  }
}

const score = (cues: Cue[], extra: Partial<Score> = {}): Score => ({ schema: SCORE_SCHEMA, duration: Math.max(...cues.map((c) => c.at + c.dur)), cues, ...extra });
const cam = (at: number, dur: number): Cue => ({ kind: 'camera', at, dur, to: { pose: { position: [0, 0, 0], target: [0, 0, -1] } } });
const sel = (at: number): Cue => ({ kind: 'select', at, dur: 0, elements: null });

describe('ScorePlayer', () => {
  it('starts a cue at its time and gives its runner the progress, 1 at the end exactly once', () => {
    const h = new FakeHost();
    const p = new ScorePlayer(h);
    const ended: boolean[] = [];
    expect(p.play(score([cam(1, 2)]), { onEnd: () => ended.push(true) })).toBe(true);
    expect(h.progress.get(0)).toBeUndefined(); // starts at t = 1
    p.advance(1);
    expect(h.progress.get(0)).toEqual([0]);
    p.advance(0.5);
    expect(h.progress.get(0)!.at(-1)).toBeCloseTo(0.25, 9);
    p.advance(1.5);
    expect(h.progress.get(0)!.at(-1)).toBe(1);
    expect(h.log.filter((l) => l === 'end 0')).toHaveLength(1);
    expect(p.playing).toBe(false);
    expect(ended).toEqual([true]);
  });

  it('runs a cue of length 0 once with progress 1, and cues of the same time in score order', () => {
    const h = new FakeHost();
    const p = new ScorePlayer(h);
    p.play(score([sel(1), cam(1, 0), sel(0)]));
    p.advance(2);
    expect(h.progress.get(0)).toEqual([1]);
    expect(h.progress.get(2)).toEqual([1]);
    const order = h.log.filter((l) => l.startsWith('start'));
    expect(order).toEqual(['start 2:select', 'start 0:select', 'start 1:camera']);
  });

  it('runs a cue that a long tick jumps over to its end', () => {
    const h = new FakeHost();
    const p = new ScorePlayer(h);
    p.play(score([cam(0, 1), cam(0.2, 0.3), sel(5)]));
    p.advance(0.2);
    p.advance(10);
    expect(h.progress.get(1)!.at(-1)).toBe(1);
    expect(h.log.filter((l) => l.startsWith('end'))).toHaveLength(3);
  });

  it('pauses the clock and resumes, and takes time from frame times with a cap per frame', () => {
    const h = new FakeHost();
    const p = new ScorePlayer(h);
    p.play(score([cam(0, 10)]));
    p.tick(1000);
    p.tick(1200);
    expect(p.time).toBeCloseTo(0.2, 9);
    p.pause();
    expect(p.paused).toBe(true);
    p.tick(2500);
    expect(p.time).toBeCloseTo(0.2, 9);
    p.resume();
    p.tick(3000); // first tick after a resume only sets the clock
    p.tick(3100);
    expect(p.time).toBeCloseTo(0.3, 9);
    p.tick(9000); // a stalled frame moves at most 250 ms
    expect(p.time).toBeCloseTo(0.55, 9);
  });

  it('restores at the end and on stop (default), not when restore is false, and keeps the camera for a user stop', () => {
    const h = new FakeHost();
    const p = new ScorePlayer(h);
    p.play(score([cam(0, 1)]));
    p.advance(2);
    expect(h.restored).toEqual([false]);
    p.play(score([cam(0, 5)]));
    p.advance(1);
    p.stop();
    expect(h.restored).toEqual([false, false]);
    p.play(score([cam(0, 5)]));
    p.stopKeepingCamera();
    expect(h.restored).toEqual([false, false, true]);
    const g = new FakeHost();
    const q = new ScorePlayer(g);
    q.play(score([cam(0, 1)]), { restore: false });
    q.advance(5);
    expect(g.restored).toEqual([]);
    expect(g.finishes).toBe(1);
  });

  it('seeks: restores, replays every cue up to the time and carries on', () => {
    const h = new FakeHost();
    const p = new ScorePlayer(h);
    p.play(score([sel(1), cam(2, 4), sel(7)]));
    p.advance(0.5);
    p.seek(4);
    expect(p.time).toBe(4);
    expect(h.restored).toEqual([false]);
    expect(h.begins).toBe(2);
    expect(h.progress.get(0)).toEqual([1]);
    expect(h.progress.get(1)!.at(-1)).toBeCloseTo(0.5, 9);
    expect(h.progress.get(2)).toBeUndefined();
    p.seek(99);
    expect(p.time).toBe(7);
    expect(h.progress.get(2)).toEqual([1]);
    p.seek(-5);
    expect(p.time).toBe(0);
  });

  it('starts at `from` by replaying the cues before it', () => {
    const h = new FakeHost();
    const p = new ScorePlayer(h);
    p.play(score([sel(1), cam(2, 4)]), { from: 3 });
    expect(p.time).toBe(3);
    expect(h.progress.get(0)).toEqual([1]);
    expect(h.progress.get(1)!.at(-1)).toBeCloseTo(0.25, 9);
  });

  it('skips a cue kind the host has no runner for, and reports started cues', () => {
    const h = new FakeHost();
    h.skip.add('label');
    h.skip.add('future-kind');
    const p = new ScorePlayer(h);
    const seen: string[] = [];
    p.play(score([{ kind: 'label', at: 0, dur: 1, elements: { all: true }, fields: ['name'] }, cam(0, 1), { kind: 'future-kind', at: 0, dur: 1 } as unknown as Cue]), { onCue: (c) => seen.push(c.kind) });
    p.advance(2);
    expect(seen).toEqual(['camera']);
  });

  it('loops: restores, starts again from 0 and keeps playing', () => {
    const h = new FakeHost();
    const p = new ScorePlayer(h);
    p.play(score([cam(0, 1)], { loop: true }));
    p.advance(1);
    expect(p.playing).toBe(true);
    expect(p.time).toBe(0);
    expect(h.begins).toBe(2);
    expect(h.progress.get(0)).toBeDefined();
  });

  it('refuses an empty score and aborts without a restore', () => {
    const h = new FakeHost();
    const p = new ScorePlayer(h);
    expect(p.play(score([], { duration: 0 }))).toBe(false);
    p.play(score([cam(0, 5)]));
    p.abort();
    expect(p.playing).toBe(false);
    expect(h.restored).toEqual([]);
  });

  it('survives a runner that throws', () => {
    const h = new FakeHost();
    h.start = () => ({ update: () => { throw new Error('boom'); } });
    const p = new ScorePlayer(h);
    p.play(score([cam(0, 1)]));
    expect(() => p.advance(2)).not.toThrow();
    expect(p.playing).toBe(false);
  });
});

describe('camera path overlay geometry', () => {
  it('draws a line through every keyframe position and a marker per keyframe', () => {
    const poses = [
      { position: [0, 0, 0], target: [0, 0, -5] },
      { position: [5, 0, 0], target: [5, 0, -5] },
      { position: [10, 2, 3], target: [10, 0, -5] },
    ] as never[];
    const g = pathGeometry(poses, 0.5);
    expect(g.line.length / 3).toBe(2 * 20 + 1);
    expect(g.line.slice(0, 3)).toEqual([0, 0, 0]);
    expect(g.line.slice(-3)).toEqual([10, 2, 3]);
    expect(g.markers).toHaveLength(3);
    expect(g.markers[0]!.length).toBe(8 * 6);
    expect(g.markers[0]!.slice(0, 3)).toEqual([0, 0, 0]);
    expect(pathGeometry([poses[0]!], 1).line).toEqual([]);
  });
});
