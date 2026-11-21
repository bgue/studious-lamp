// A 4D film: one `schedule4d` cue over the plan's length, plus the cues of a script when one is given. Pure. Used by the packed page's
// autoplay (plugins/boot.ts) and by `xray-4d render` (window.__xray4dFilm).

import type { FourDPlan } from '../../schedule/types';
import { SCORE_SCHEMA, scoreEnd } from '../score';
import type { Score } from '../score';

/** Seconds of the plan on screen: the end of its time map (at least 1). */
export function planSeconds(plan: FourDPlan): number {
  const last = plan.timeMap[plan.timeMap.length - 1];
  return Math.max(1, last ? last[1] : 1);
}

/**
 * The film score of a registered plan. The script's own `schedule4d` cues are dropped (the plan is the film's clock); its other cues
 * (camera, captions, tint ...) are kept. `script` null: the plan alone.
 */
export function planFilm(plan: FourDPlan, name: string, script?: Score | null, loop = false): Score {
  const secs = planSeconds(plan);
  const cues: Score['cues'] = [{ at: 0, dur: secs, kind: 'schedule4d', plan: { name } }];
  if (script) for (const c of script.cues) if (c.kind !== 'schedule4d') cues.push(c);
  return { schema: SCORE_SCHEMA, duration: Math.max(secs, scoreEnd(cues), script?.duration ?? 0), cues, ...(loop ? { loop: true } : {}) };
}
