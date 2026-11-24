// Run a script through the score player. Pure apart from the player it is given (src/anim/score.ts getScorePlayer()).

import type { Cue, Score, ScorePlayerApi } from '../score';
import { compileScript } from './compiler';
import type { CompileOptions } from './compiler';
import { formatDiagnostic } from './diagnostics';
import type { ScriptDiagnostic } from './diagnostics';

export interface RunHooks {
  /** The script line of the cue that started, or null when playback ended. */
  onLine?(line: number | null, cue?: Cue): void;
  onEnd?(): void;
}

export interface RunResult {
  ok: boolean;
  /** For the status line. */
  message: string;
  errors: ScriptDiagnostic[];
  score: Score | null;
}

export const NO_PLAYER_MESSAGE = 'The score player is not available in this build, so the script cannot run.';

/** Compile `text` and hand the score to `player`. Never throws. */
export function runScript(text: string, opts: CompileOptions, player: ScorePlayerApi | null, hooks: RunHooks = {}): RunResult {
  const { score, errors } = compileScript(text, opts);
  if (!score) {
    const first = errors.find((e) => e.severity === 'error');
    return { ok: false, message: first ? formatDiagnostic(first) : 'The script has errors.', errors, score: null };
  }
  if (!player) return { ok: false, message: NO_PLAYER_MESSAGE, errors, score };
  if (score.cues.length === 0) return { ok: false, message: 'The script makes no steps: nothing to play.', errors, score };
  let started = false;
  try {
    started = player.play(score, {
      onCue: (cue) => hooks.onLine?.(cue.line ?? null, cue),
      onEnd: () => {
        hooks.onLine?.(null);
        hooks.onEnd?.();
      },
    });
  } catch (e) {
    return { ok: false, message: `The player failed: ${e instanceof Error ? e.message : String(e)}`, errors, score };
  }
  if (!started) return { ok: false, message: 'The player did not start (it may be busy).', errors, score };
  return { ok: true, message: `Playing: ${score.cues.length} step${score.cues.length === 1 ? '' : 's'}, ${Math.round(score.duration * 10) / 10} seconds.`, errors, score };
}
