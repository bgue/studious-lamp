// The score player core: plays a Score (src/anim/score.ts) on a clock. It knows nothing about the viewer: a PlayerHost starts a
// runner for each cue (camera, settings, visibility, selection, captions: src/anim/viewerHost.ts) and restores the state that
// existed before play. The core owns the clock, pause, seek, loop, the cue order and the end. Pure, tested with a fake host in
// tests/anim-player.test.ts.
//
// A cue starts when the clock reaches its `at`; from then its runner gets the raw progress 0..1 on every tick until the cue
// ends (progress 1), which runs once, also when a tick jumps over the whole cue. Cues of the same time run in score order. A
// cue kind that the host has no runner for is skipped. A seek restores the state first and replays every cue up to the new time.

import type { Cue, PlayOptions, Score, ScorePlayerApi } from './score';
import { scoreEnd } from './score';

export interface CueRunner {
  /** Raw progress 0..1 of the cue (0 at its start, 1 when it is over; a cue of length 0 gets 1 once). */
  update(progress: number): void;
  /** Called once when the cue is over, after the update(1). */
  end?(): void;
}

export interface PlayerHost {
  /** Playback begins: keep what `restore` needs and resolve the element references of the score. */
  begin(score: Score, opts?: PlayOptions): void;
  /** A runner for a cue that starts, or null to skip it. */
  start(cue: Cue, index: number): CueRunner | null;
  /** Put the state back as it was at begin(). `keepCamera`: leave the camera where it is (the user took over). */
  restore(keepCamera: boolean): void;
  /** Playback ended or stopped (hide the captions, drop the fades). Runs before restore. */
  finish(): void;
  /** Playback is abandoned without a restore (the model changed): forget everything held for it. */
  abandon?(): void;
  /** Called at the end of every tick with the clock time (apply what the runners collected this frame). */
  flush?(time: number): void;
}

interface CueState {
  cue: Cue;
  index: number;
  runner: CueRunner | null;
  started: boolean;
  done: boolean;
}

export class ScorePlayer implements ScorePlayerApi {
  private score: Score | null = null;
  private opts: PlayOptions = {};
  private states: CueState[] = [];
  private t = 0;
  private isPlaying = false;
  private isPaused = false;
  private lastNow: number | null = null;

  constructor(private readonly host: PlayerHost) {}

  get playing(): boolean {
    return this.isPlaying;
  }

  get paused(): boolean {
    return this.isPaused;
  }

  get time(): number {
    return this.t;
  }

  get duration(): number {
    return this.score ? Math.max(this.score.duration, scoreEnd(this.score.cues)) : 0;
  }

  get current(): Score | null {
    return this.score;
  }

  play(score: Score, opts: PlayOptions = {}): boolean {
    if (!score || !Array.isArray(score.cues) || score.cues.length === 0) return false;
    if (this.isPlaying) this.finishRun(opts.restore === false ? false : true, false);
    this.score = score;
    this.opts = opts;
    this.host.begin(score, opts);
    this.isPlaying = true;
    this.isPaused = false;
    this.lastNow = null;
    this.reset();
    const from = Math.max(0, opts.from ?? 0);
    this.t = 0;
    if (from > 0) this.replayTo(from);
    else this.process();
    return true;
  }

  stop(): void {
    this.finishRun(this.opts.restore !== false, false);
  }

  /** Stop because the user took over the camera: the camera stays, everything else goes back. */
  stopKeepingCamera(): void {
    this.finishRun(this.opts.restore !== false, true);
  }

  /** Drop the run without restoring anything (the model changed under it). */
  abort(): void {
    if (!this.isPlaying) return;
    this.isPlaying = false;
    this.isPaused = false;
    this.host.abandon?.();
    const cb = this.opts.onEnd;
    this.states = [];
    this.opts = {};
    cb?.();
  }

  pause(): void {
    if (this.isPlaying) this.isPaused = true;
  }

  resume(): void {
    if (!this.isPlaying) return;
    this.isPaused = false;
    this.lastNow = null;
  }

  seek(t: number): void {
    if (!this.score) return;
    const end = this.duration;
    this.replayTo(Math.min(Math.max(0, t), end));
  }

  /** Advance the clock to `nowMs` (a frame time). Call once per frame while playing. */
  tick(nowMs: number): void {
    if (!this.isPlaying) return;
    const last = this.lastNow;
    this.lastNow = nowMs;
    if (this.isPaused || last === null) return;
    const dt = Math.min(Math.max(nowMs - last, 0), 250) / 1000;
    this.advance(dt);
  }

  /** Advance by dt seconds (tick() calls it; tests call it directly). */
  advance(dt: number): void {
    if (!this.isPlaying || this.isPaused || !this.score) return;
    this.t += dt;
    const end = this.duration;
    if (this.t >= end) {
      this.t = end;
      this.process();
      if (this.score?.loop) {
        this.host.finish();
        this.host.restore(false);
        this.reset();
        this.t = 0;
        this.host.begin(this.score, this.opts);
        this.process();
        return;
      }
      this.finishRun(this.opts.restore !== false, false);
      return;
    }
    this.process();
  }

  // ---------------------------------------------------------------- internals

  private reset(): void {
    const cues = this.score?.cues ?? [];
    this.states = cues
      .map((cue, index): CueState => ({ cue, index, runner: null, started: false, done: false }))
      .sort((a, b) => a.cue.at - b.cue.at || a.index - b.index);
  }

  /** Run every cue that has started by the clock: the ones starting now, the ones in progress and the ones that ended. */
  private process(): void {
    const t = this.t;
    for (const s of this.states) {
      if (s.done) continue;
      if (s.cue.at > t + 1e-9) break;
      if (!s.started) {
        s.started = true;
        try {
          s.runner = this.host.start(s.cue, s.index);
        } catch (e) {
          console.warn('score player: cue failed to start', s.cue.kind, e);
          s.runner = null;
        }
        if (s.runner) this.opts.onCue?.(s.cue, s.index);
      }
      const dur = Math.max(0, s.cue.dur);
      const p = dur > 1e-9 ? Math.min(1, Math.max(0, (t - s.cue.at) / dur)) : 1;
      if (s.runner) {
        try {
          s.runner.update(p);
          if (p >= 1) s.runner.end?.();
        } catch (e) {
          console.warn('score player: cue failed', s.cue.kind, e);
        }
      }
      if (p >= 1) s.done = true;
    }
    this.host.flush?.(t);
  }

  private replayTo(t: number): void {
    this.host.finish();
    this.host.restore(false);
    this.host.begin(this.score!, this.opts);
    this.reset();
    this.t = t;
    this.lastNow = null;
    this.process();
  }

  private finishRun(restore: boolean, keepCamera: boolean): void {
    if (!this.isPlaying) return;
    this.isPlaying = false;
    this.isPaused = false;
    // Whatever still runs ends at its final state, so a stop in the middle of a fade leaves no half-way elements.
    this.host.finish();
    if (restore) this.host.restore(keepCamera);
    const cb = this.opts.onEnd;
    this.states = [];
    this.opts = {};
    cb?.();
  }
}
